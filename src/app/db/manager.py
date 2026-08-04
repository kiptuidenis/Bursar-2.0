import hashlib
import secrets
import time
import os
import datetime
import logging
from typing import Dict, List, Any, Optional

from sqlalchemy import create_engine, func, event
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, User, Settings, Payout, Log, BudgetItem, Deposit, Session, IdempotencyRecord, Notification, OtpCode

logger = logging.getLogger(__name__)



def _row_to_dict(model_instance, fields=None):
    if not model_instance:
        return {}
    res = {}
    cols = fields if fields else [c.name for c in model_instance.__table__.columns]
    for col in cols:
        val = getattr(model_instance, col)
        if isinstance(val, datetime.datetime):
            res[col] = val.strftime("%Y-%m-%d %H:%M:%S")
        else:
            res[col] = val
    return res

_engines_cache = {}

def sanitize_db_url(url: str) -> str:
    """
    Parse a database URL and automatically URL-encode any special characters in the password.
    Supports both mysql:// and mysql+pymysql:// schemes.
    """
    if not (url.startswith("mysql://") or url.startswith("mysql+pymysql://")):
        return url
        
    scheme = "mysql+pymysql://"
    prefix_len = len("mysql://")
    if url.startswith("mysql+pymysql://"):
        prefix_len = len("mysql+pymysql://")
        
    rest = url[prefix_len:]
    
    # Split the authority component (userinfo@host) from the rest of the path (database, query params etc.)
    path_split = rest.split("/", 1)
    authority = path_split[0]
    path = path_split[1] if len(path_split) > 1 else ""
    
    if "@" in authority:
        # The last '@' symbol in the authority separates userinfo (user:password) from hostinfo
        userinfo, host = authority.rsplit("@", 1)
        if ":" in userinfo:
            from urllib.parse import quote_plus, unquote
            username, password = userinfo.split(":", 1)
            # Safely unquote first to prevent double-encoding, then quote_plus
            username = quote_plus(unquote(username))
            password = quote_plus(unquote(password))
            authority = f"{username}:{password}@{host}"
            
    return f"{scheme}{authority}/{path}"

class DatabaseManager:
    def __init__(self, db_path: str = "bursar.db"):
        self.db_path = db_path
        
        # Format database path/URL
        if db_path.startswith("mysql://") or db_path.startswith("mysql+pymysql://"):
            self.db_url = sanitize_db_url(db_path)
        elif "://" not in db_path:
            abs_path = os.path.abspath(db_path).replace("\\", "/")
            self.db_url = f"sqlite:///{abs_path}"
        else:
            self.db_url = db_path
            
        self._session = None
        self._raw_conn = None

    @property
    def engine(self):
        global _engines_cache
        if self.db_url not in _engines_cache:
            connect_args = {}
            engine_kwargs = {}
            if self.db_url.startswith("sqlite"):
                connect_args["check_same_thread"] = False
            else:
                # Enable pre-ping and recycle to prevent stale RDS MySQL connection drops
                engine_kwargs["pool_pre_ping"] = True
                engine_kwargs["pool_recycle"] = 3600

            engine = create_engine(self.db_url, connect_args=connect_args, **engine_kwargs)
            
            # Register SQLite performance tuning pragmas
            if self.db_url.startswith("sqlite"):
                @event.listens_for(engine, "connect")
                def set_sqlite_pragma(dbapi_connection, connection_record):
                    import sqlite3
                    if isinstance(dbapi_connection, sqlite3.Connection):
                        cursor = dbapi_connection.cursor()
                        cursor.execute("PRAGMA foreign_keys = ON")
                        
                        is_pytest = (
                            "TESTING" in os.environ 
                            or "PYTEST_CURRENT_TEST" in os.environ
                        )
                        if is_pytest:
                            try:
                                cursor.execute("PRAGMA synchronous = OFF")
                                cursor.execute("PRAGMA journal_mode = MEMORY")
                            except Exception:
                                pass
                        else:
                            try:
                                cursor.execute("PRAGMA journal_mode = WAL")
                            except Exception:
                                pass
                        cursor.close()
            _engines_cache[self.db_url] = engine
        return _engines_cache[self.db_url]

    @property
    def SessionLocal(self):
        return sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    @property
    def session(self):
        if self._session is None:
            self._session = self.SessionLocal()
        return self._session

    @property
    def connection(self):
        """Expose raw driver connection for temporary backwards compatibility."""
        if self._raw_conn is None:
            raw_conn = self.engine.raw_connection()
            if self.engine.dialect.name == "sqlite":
                import sqlite3
                actual_conn = raw_conn
                if hasattr(raw_conn, "driver_connection"):
                    actual_conn = raw_conn.driver_connection
                elif hasattr(raw_conn, "connection"):
                    actual_conn = raw_conn.connection
                actual_conn.row_factory = sqlite3.Row
            self._raw_conn = raw_conn
        return self._raw_conn

    def _commit(self) -> None:
        """Helper to commit transactions and rollback on exceptions to keep the session clean."""
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def initialize(self) -> None:
        """Initialize database schema tables and auto-migrate missing columns for existing tables."""
        Base.metadata.create_all(bind=self.engine)
        self._auto_migrate_columns()

    def _auto_migrate_columns(self) -> None:
        """Auto-migrate missing columns for existing tables in production (MySQL & SQLite)."""
        from sqlalchemy import inspect, text
        try:
            inspector = inspect(self.engine)
            if not inspector.has_table("users"):
                return

            columns = [c["name"] for c in inspector.get_columns("users")]
            with self.engine.begin() as conn:
                if self.engine.name == "mysql":
                    try:
                        conn.execute(text("ALTER TABLE users MODIFY COLUMN phone_number VARCHAR(50) NULL DEFAULT NULL"))
                    except Exception as e:
                        logger.warning(f"Failed to modify phone_number column nullability on MySQL: {e}")
                if "email" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL"))
                if "failed_login_attempts" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN failed_login_attempts INT DEFAULT 0"))
                if "account_locked_until" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN account_locked_until VARCHAR(50) DEFAULT ''"))
                if "email_verified" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
                if "two_factor_enabled" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN DEFAULT 1"))
                if "payout_phone_number" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN payout_phone_number VARCHAR(50) DEFAULT ''"))
        except Exception:
            pass

    # Cryptographic Hashing Helpers
    def _hash_password(self, password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """Hash a plaintext password using Argon2id with OWASP ASVS recommended cost parameters."""
        from app.core.password import hash_password_argon2
        return hash_password_argon2(password), "argon2"

    def _hash_password_pbkdf2_legacy(self, password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """Legacy helper: Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
        if salt is None:
            salt = secrets.token_bytes(16)
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            100000
        )
        return hash_bytes.hex(), salt.hex()

    def _verify_password(self, password: str, password_hash_hex: str, salt_hex: str = "") -> bool:
        """Verify password against stored hash (Argon2id or legacy PBKDF2)."""
        if password_hash_hex and password_hash_hex.startswith("$argon2id$"):
            from app.core.password import verify_password_argon2
            return verify_password_argon2(password, password_hash_hex)

        # Legacy PBKDF2 verification using constant-time comparison (SEC-001)
        import hmac
        try:
            salt = bytes.fromhex(salt_hex)
            hash_bytes = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                100000
            )
            return hmac.compare_digest(hash_bytes.hex().encode('utf-8'), password_hash_hex.encode('utf-8'))
        except Exception:
            return False

    # User Auth Operations
    def create_user_email(self, email: str, password_plaintext: str, payout_phone: Optional[str] = None) -> int:
        """Register a new user using email address, hashes password with Argon2id, and initializes settings."""
        email_clean = email.strip().lower()
        existing = self.session.query(User).filter(User.email == email_clean).first()
        if existing:
            raise ValueError(f"An account with email '{email_clean}' already exists.")
            
        password_hash, salt = self._hash_password(password_plaintext)
        
        try:
            db_user = User(
                email=email_clean,
                password_hash=password_hash,
                salt=salt,
                phone_number=None,
                payout_phone_number=payout_phone or "",
                email_verified=False,
                two_factor_enabled=True
            )
            self.session.add(db_user)
            self.session.flush()
            
            db_settings = Settings(
                user_id=db_user.id,
                phone_number=payout_phone or ""
            )
            self.session.add(db_settings)
            self._commit()
            return db_user.id
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error creating user with email '{email_clean}': {e}", exc_info=True)
            raise ValueError(f"Could not create user account: {str(e)}")

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Fetch user ORM model instance by email address."""
        if not email:
            return None
        return self.session.query(User).filter(User.email == email.strip().lower()).first()

    def update_payout_phone_number(self, user_id: int, phone_number: str):
        """Update payout Safaricom phone number for financial disbursements."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if user:
            user.payout_phone_number = phone_number
            settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
            if settings:
                settings.phone_number = phone_number
            self._commit()

    def get_payout_phone_number(self, user_id: int) -> Optional[str]:
        """Get stored payout phone number for a user."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if user and user.payout_phone_number:
            return user.payout_phone_number
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if settings:
            return settings.phone_number
        return ""

    def create_otp_challenge(self, email: str, purpose: str, ttl_seconds: int = 300, user_id: Optional[int] = None) -> str:
        """
        Generate a cryptographically secure 6-digit numeric OTP challenge,
        store Argon2id hashed code in `otp_codes` table, and return raw code for email delivery.
        """
        email_clean = email.strip().lower()
        if not user_id:
            user = self.get_user_by_email(email_clean)
            if user:
                user_id = user.id
                
        # Invalidate any active pending OTP challenges for this email and purpose
        self.session.query(OtpCode).filter(
            OtpCode.email == email_clean,
            OtpCode.purpose == purpose
        ).delete(synchronize_session=False)
        self._commit()

        # Generate 6-digit numeric code
        otp_raw = f"{secrets.randbelow(1000000):06d}"
        
        # Hash code using Argon2id
        otp_hash, _ = self._hash_password(otp_raw)
        
        expires_at_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=ttl_seconds)
        expires_str = expires_at_dt.strftime("%Y-%m-%d %H:%M:%S")
        created_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        otp_record = OtpCode(
            user_id=user_id,
            email=email_clean,
            otp_code_hash=otp_hash,
            purpose=purpose,
            expires_at=expires_str,
            attempts=0,
            created_at=created_str
        )
        self.session.add(otp_record)
        self._commit()
        return otp_raw

    def verify_otp_challenge(self, email: str, otp_code: str, purpose: str) -> bool:
        """
        Validate a 6-digit OTP code against the database challenge.
        Checks expiration, attempt limits (max 3 attempts), and sets `email_verified=True` upon success.
        """
        email_clean = email.strip().lower()
        record = self.session.query(OtpCode).filter(
            OtpCode.email == email_clean,
            OtpCode.purpose == purpose
        ).order_by(OtpCode.id.desc()).first()
        
        if not record:
            return False

        # 1. Check expiration
        try:
            expires_dt = datetime.datetime.strptime(record.expires_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            if now_dt > expires_dt:
                self.session.delete(record)
                self._commit()
                return False
        except Exception:
            return False

        # 2. Check attempt limits
        if record.attempts >= 3:
            self.session.delete(record)
            self._commit()
            return False

        # 3. Verify OTP code hash
        is_valid = self._verify_password(otp_code, record.otp_code_hash)
        if not is_valid:
            record.attempts += 1
            self._commit()
            return False

        # Verification successful! Delete used OTP challenge record
        self.session.delete(record)
        
        # Mark user email as verified
        user = self.session.query(User).filter(User.email == email_clean).first()
        if user:
            user.email_verified = True
            
        self._commit()
        return True

    def create_user(self, phone_number: str, password_plaintext: str) -> int:
        """Register a new user, hashes password using Argon2id, and creates default settings row."""
        password_hash, salt = self._hash_password(password_plaintext)
        
        db_user = User(
            phone_number=phone_number,
            password_hash=password_hash,
            salt=salt
        )
        self.session.add(db_user)
        self._commit()
        
        # Create user's settings profile automatically (defaulting settings phone number to registration phone number)
        db_settings = Settings(
            user_id=db_user.id,
            phone_number=phone_number
        )
        self.session.add(db_settings)
        self._commit()
        return db_user.id

    def is_account_locked(self, phone_number: str) -> tuple[bool, int]:
        """Check if an account is locked due to 5+ failed login attempts. Returns (is_locked, remaining_seconds)."""
        user = self.session.query(User).filter(User.phone_number == phone_number).first()
        if not user or not user.account_locked_until:
            return False, 0
            
        try:
            locked_until_dt = datetime.datetime.strptime(user.account_locked_until, "%Y-%m-%d %H:%M:%S")
            now_dt = datetime.datetime.utcnow()
            if now_dt < locked_until_dt:
                remaining = int((locked_until_dt - now_dt).total_seconds())
                return True, max(remaining, 1)
            else:
                user.account_locked_until = ""
                user.failed_login_attempts = 0
                self._commit()
                return False, 0
        except Exception:
            return False, 0

    def record_failed_login_attempt(self, phone_number: str) -> tuple[int, bool]:
        """Increment failed login attempts counter. Locks account for 15 mins if 5 attempts reached. Returns (attempts, is_locked)."""
        user = self.session.query(User).filter(User.phone_number == phone_number).first()
        if not user:
            return 0, False
            
        current = user.failed_login_attempts or 0
        current += 1
        user.failed_login_attempts = current
        
        is_locked = False
        if current >= 5:
            is_locked = True
            lock_duration = datetime.timedelta(minutes=15)
            user.account_locked_until = (datetime.datetime.utcnow() + lock_duration).strftime("%Y-%m-%d %H:%M:%S")
            self.log_event(user.id, "WARNING", f"Account locked for 15 minutes due to {current} consecutive failed PIN attempts.")
            
        self._commit()
        return current, is_locked

    def reset_failed_login_attempts(self, phone_number: str) -> None:
        """Reset failed login attempts counter and clear lockout state on successful authentication."""
        user = self.session.query(User).filter(User.phone_number == phone_number).first()
        if user and (user.failed_login_attempts > 0 or user.account_locked_until):
            user.failed_login_attempts = 0
            user.account_locked_until = ""
            self._commit()

    def authenticate_user(self, phone_number: str, password_plaintext: str) -> Optional[int]:
        """Authenticate user credentials. Transparently upgrades legacy PBKDF2 hashes to Argon2id upon successful authentication."""
        user = self.session.query(User).filter(User.phone_number == phone_number).first()
        if not user:
            return None
            
        if self._verify_password(password_plaintext, user.password_hash, user.salt):
            # Transparent re-hashing migration for legacy PBKDF2 users
            if not user.password_hash.startswith("$argon2id$"):
                new_hash, new_salt = self._hash_password(password_plaintext)
                user.password_hash = new_hash
                user.salt = new_salt
                self._commit()
            return user.id
        return None

    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch user profile details."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        data = _row_to_dict(user)
        if data.get("email") is None:
            data["email"] = ""
        return data

    def update_profile(self, user_id: int, **kwargs: Any) -> None:
        """Update user profile fields."""
        if not kwargs:
            return
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            return
        allowed_fields = {"first_name", "last_name", "email", "avatar_url", "bio", "theme", "notifications_enabled"}
        for key, val in kwargs.items():
            if key in allowed_fields:
                setattr(user, key, val)
        self._commit()

    def update_password(self, user_id: int, new_password_plaintext: str) -> None:
        """Update user's password PIN."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            return
        password_hash, salt = self._hash_password(new_password_plaintext)
        user.password_hash = password_hash
        user.salt = salt
        self._commit()

    def create_session_db(self, user_id: int, token: str, user_agent: str, ip_address: str, expires_at: int) -> None:
        """Insert a session token record in database."""
        current_time = int(time.time())
        db_session = Session(
            user_id=user_id,
            session_token=token,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=expires_at,
            last_activity=current_time
        )
        self.session.add(db_session)
        self._commit()

    def get_active_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Retrieve all active session records for a user."""
        sessions = self.session.query(Session).filter(
            Session.user_id == user_id,
            Session.expires_at > int(time.time())
        ).order_by(Session.created_at.desc()).all()
        return [_row_to_dict(s) for s in sessions]

    def revoke_session(self, user_id: int, session_id: int) -> bool:
        """Revoke a specific session for a user by session record ID."""
        session = self.session.query(Session).filter(
            Session.user_id == user_id,
            Session.id == session_id
        ).first()
        if session:
            self.session.delete(session)
            self._commit()
            return True
        return False

    def revoke_other_sessions(self, user_id: int, current_token: str) -> None:
        """Revoke all sessions except the current one for a user."""
        self.session.query(Session).filter(
            Session.user_id == user_id,
            Session.session_token != current_token
        ).delete(synchronize_session=False)
        self._commit()

    def verify_session_token_db(self, token: str, is_poll: bool = False) -> Optional[int]:
        """Verify the token exists in DB and is active, checking inactivity timeout."""
        now = int(time.time())
        session = self.session.query(Session).filter(
            Session.session_token == token,
            Session.expires_at > now
        ).first()
        if not session:
            return None
            
        user_id = session.user_id
        last_act = session.last_activity
        if last_act is None:
            last_act = session.expires_at - 86400
            
        # Inactivity check: 5 minutes (300 seconds)
        if now - last_act > 300:
            self.session.delete(session)
            self._commit()
            return None
            
        # If valid and not a background poll, update last activity to now
        if not is_poll:
            session.last_activity = now
            self._commit()
            
        return user_id

    def cleanup_expired_sessions(self, inactivity_timeout_seconds: int = 300) -> None:
        """Delete sessions that are expired absolutely or idle for too long."""
        now = int(time.time())
        sessions = self.session.query(Session).all()
        to_delete = []
        for s in sessions:
            if s.expires_at < now:
                to_delete.append(s)
            else:
                last_act = s.last_activity if s.last_activity is not None else (s.expires_at - 86400)
                if now - last_act > inactivity_timeout_seconds:
                    to_delete.append(s)
        
        for s in to_delete:
            self.session.delete(s)
        if to_delete:
            self._commit()

    def deactivate_user(self, user_id: int) -> None:
        """Permanently delete user account and trigger cascading deletions."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if user:
            self.session.delete(user)
            self._commit()

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Fetch all user profiles (useful for the background scheduler run)."""
        users = self.session.query(User).all()
        return [{"id": u.id, "phone_number": u.phone_number} for u in users]

    # Settings Operations (Isolated per user)
    def get_settings(self, user_id: int, decrypt_secrets: bool = True) -> Dict[str, Any]:
        """Retrieve the configuration settings for a specific user."""
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if not settings:
            return {}
        data = _row_to_dict(settings)
        if decrypt_secrets:
            from app.core.encryption import decrypt_credential
            if data.get("mpesa_consumer_secret"):
                data["mpesa_consumer_secret"] = decrypt_credential(data["mpesa_consumer_secret"])
            if data.get("mpesa_initiator_password"):
                data["mpesa_initiator_password"] = decrypt_credential(data["mpesa_initiator_password"])
        return data

    def update_settings(self, user_id: int, **kwargs: Any) -> None:
        """Dynamically update settings columns for a specific user, encrypting sensitive fields at rest."""
        if not kwargs:
            return
        
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if not settings:
            return
            
        from app.core.encryption import encrypt_credential
        for key, val in kwargs.items():
            if key == "user_id":
                continue
            if key in ("mpesa_consumer_secret", "mpesa_initiator_password"):
                if val == "********":
                    # Ignore masked placeholder sent by frontend; preserve existing encrypted secret
                    continue
                if isinstance(val, str) and val.strip():
                    val = encrypt_credential(val)
            if hasattr(settings, key):
                setattr(settings, key, val)
        self._commit()

    def adjust_balance(self, user_id: int, amount: int | float) -> None:
        """Add or subtract from the current wallet balance of a specific user using atomic SQL arithmetic."""
        int_amount = int(amount)
        self.session.query(Settings).filter(
            Settings.user_id == user_id
        ).update({
            Settings.balance: Settings.balance + int_amount
        }, synchronize_session=False)
        self._commit()
        if int_amount > 0:
            self.resolve_low_balance_warnings(user_id)

    def resolve_low_balance_warnings(self, user_id: int) -> None:
        """Mark low balance warning notifications as read if updated balance meets daily budget allocation."""
        settings = self.get_settings(user_id)
        if not settings:
            return
        balance = int(settings.get("balance", 0))
        daily_budget = int(settings.get("daily_budget", 0))
        if balance >= daily_budget and daily_budget > 0:
            notifications = (
                self.session.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.type == "WARNING",
                    Notification.is_read == False
                )
                .all()
            )
            for notif in notifications:
                if "Payout Skipped" in notif.title or "Low Balance" in notif.title:
                    notif.is_read = True
            self._commit()

    def is_budget_locked(self, user_id: int, today: Optional[datetime.date] = None) -> bool:
        """Check if the user's budget allocations are locked for the current calendar month or active schedule."""
        settings = self.get_settings(user_id)
        if not settings:
            return False
            
        import datetime
        ref_date = today or datetime.date.today()
        ref_str = ref_date.strftime("%Y-%m-%d")
        
        # If an explicit payout schedule end_date exists and ref_str > end_date, budget schedule has ended & budget is unlocked
        end_date = settings.get("end_date", "")
        if end_date and ref_str > end_date:
            return False

        locked_until = settings.get("budget_locked_until", "")
        if not locked_until:
            return False
        try:
            lock_date = datetime.datetime.strptime(locked_until, "%Y-%m-%d").date()
            return ref_date <= lock_date
        except ValueError:
            return False

    def is_deposit_locked(self, user_id: int) -> bool:
        """Check if the user's deposited funds are locked for the current calendar month."""
        settings = self.get_settings(user_id)
        if not settings:
            return False
        locked_until = settings.get("deposit_locked_until", "")
        if not locked_until:
            return False
        import datetime
        try:
            lock_date = datetime.datetime.strptime(locked_until, "%Y-%m-%d").date()
            return datetime.date.today() < lock_date
        except ValueError:
            return False

    def _get_first_of_next_month(self) -> str:
        """Calculate the first day of the next calendar month as 'YYYY-MM-DD'."""
        import datetime
        dt = datetime.date.today()
        if dt.month == 12:
            next_month = datetime.date(dt.year + 1, 1, 1)
        else:
            next_month = datetime.date(dt.year, dt.month + 1, 1)
        return next_month.strftime("%Y-%m-%d")

    def lock_budget(self, user_id: int) -> None:
        """Lock the budget configuration until the first day of the next calendar month."""
        lock_date = self._get_first_of_next_month()
        self.update_settings(user_id, budget_locked_until=lock_date)

    def lock_deposit(self, user_id: int) -> None:
        """Lock the deposit balance until the first day of the next calendar month."""
        lock_date = self._get_first_of_next_month()
        self.update_settings(user_id, deposit_locked_until=lock_date)

    # Payout Operations (Isolated per user)
    def create_payout(self, user_id: int, payout_date: str, amount: float, phone_number: str, 
                      status: str, conversation_id: str = "", 
                      originator_conversation_id: str = "") -> int:
        """Create a new payout transaction log. Raises IntegrityError on duplicate date per user."""
        payout = Payout(
            user_id=user_id,
            payout_date=payout_date,
            amount=amount,
            phone_number=phone_number,
            status=status,
            conversation_id=conversation_id,
            originator_conversation_id=originator_conversation_id
        )
        self.session.add(payout)
        self._commit()
        return payout.id

    def update_payout_status(self, conversation_id: str, status: str,
                             transaction_id: str = "", error_message: str = "",
                             completed_at: str = "", failed_at: str = "") -> bool:
        """Atomically update payout record status by ConversationID ONLY if current status is PENDING."""
        rows_updated = self.session.query(Payout).filter(
            Payout.conversation_id == conversation_id,
            Payout.status == 'PENDING'
        ).update({
            Payout.status: status,
            Payout.transaction_id: transaction_id,
            Payout.error_message: error_message,
            Payout.completed_at: completed_at,
            Payout.failed_at: failed_at
        }, synchronize_session=False)
        self._commit()
        return rows_updated > 0

    def get_payout_by_user_date(self, user_id: int, payout_date: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific payout record for a user on a given date (YYYY-MM-DD)."""
        payout = self.session.query(Payout).filter(
            Payout.user_id == user_id,
            Payout.payout_date == payout_date
        ).first()
        return _row_to_dict(payout) if payout else None

    def reset_failed_payout_for_retry(self, payout_id: int) -> None:
        """Reset a FAILED payout record back to PENDING so a retry can proceed."""
        payout = self.session.query(Payout).filter(
            Payout.id == payout_id,
            Payout.status == 'FAILED'
        ).first()
        if payout:
            payout.status = 'PENDING'
            payout.conversation_id = ''
            payout.originator_conversation_id = ''
            payout.transaction_id = ''
            payout.error_message = ''
            payout.failed_at = ''
            self._commit()

    def get_payout_by_conversation_id(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific payout transaction by conversation ID across all users."""
        payout = self.session.query(Payout).filter(Payout.conversation_id == conversation_id).first()
        return _row_to_dict(payout) if payout else None

    def get_payouts(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch past payouts for a specific user, sorted by created_at DESC, id DESC."""
        payouts = self.session.query(Payout).filter(Payout.user_id == user_id).order_by(
            Payout.created_at.desc(),
            Payout.id.desc()
        ).limit(limit).all()
        return [_row_to_dict(p) for p in payouts]

    # Logging Operations (Isolated per user)
    def log_event(self, user_id: int, level: str, message: str) -> None:
        """Write a system event to logs for a specific user."""
        log = Log(
            user_id=user_id,
            level=level,
            message=message
        )
        self.session.add(log)
        self._commit()

    def get_logs(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch system logs for a specific user, sorted by id DESC."""
        logs = self.session.query(Log).filter(Log.user_id == user_id).order_by(Log.id.desc()).limit(limit).all()
        return [_row_to_dict(l) for l in logs]

    def get_budget_items(self, user_id: int) -> List[Dict[str, Any]]:
        """Fetch all budget allocation items for a specific user."""
        items = self.session.query(BudgetItem).filter(BudgetItem.user_id == user_id).order_by(BudgetItem.category.asc()).all()
        return [_row_to_dict(i) for i in items]

    def add_or_update_budget_item(self, user_id: int, category: str, amount: float) -> int:
        """Add a new budget allocation item or update it if the category already exists."""
        item = self.session.query(BudgetItem).filter(
            BudgetItem.user_id == user_id,
            BudgetItem.category == category
        ).first()
        if item:
            item.amount = amount
        else:
            item = BudgetItem(
                user_id=user_id,
                category=category,
                amount=amount
            )
            self.session.add(item)
        self._commit()
        item_id = item.id
        self.recalculate_daily_budget(user_id)
        return item_id

    def delete_budget_item(self, user_id: int, item_id: int) -> bool:
        """Delete a specific budget allocation item for a user."""
        item = self.session.query(BudgetItem).filter(
            BudgetItem.user_id == user_id,
            BudgetItem.id == item_id
        ).first()
        if item:
            self.session.delete(item)
            self._commit()
            self.recalculate_daily_budget(user_id)
            return True
        return False

    def recalculate_daily_budget(self, user_id: int) -> float:
        """Sum all allocation items and update the user's daily budget settings."""
        total = self.session.query(func.sum(BudgetItem.amount)).filter(BudgetItem.user_id == user_id).scalar()
        if total is None:
            total = 0.0
            
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if settings:
            settings.daily_budget = total
            self._commit()
            
        self.log_event(user_id, "INFO", f"Recalculated daily budget allocation total: KES {total:.2f}.")
        return total

    def create_deposit(self, user_id: int, checkout_request_id: str, amount: float) -> int:
        """Create a pending deposit transaction record."""
        deposit = Deposit(
            user_id=user_id,
            checkout_request_id=checkout_request_id,
            amount=amount,
            status='PENDING'
        )
        self.session.add(deposit)
        self._commit()
        return deposit.id

    def get_deposit(self, checkout_request_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a deposit record by its checkout request ID."""
        deposit = self.session.query(Deposit).filter(Deposit.checkout_request_id == checkout_request_id).first()
        return _row_to_dict(deposit) if deposit else None

    def update_deposit_status(self, checkout_request_id: str, status: str, mpesa_receipt: str = "") -> bool:
        """Atomically update the status and M-Pesa receipt of a deposit transaction ONLY if current status is PENDING."""
        rows_updated = self.session.query(Deposit).filter(
            Deposit.checkout_request_id == checkout_request_id,
            Deposit.status == 'PENDING'
        ).update({
            Deposit.status: status,
            Deposit.mpesa_receipt: mpesa_receipt
        }, synchronize_session=False)
        self._commit()
        return rows_updated > 0

    def get_idempotency_record(self, user_id: int, key: str, endpoint: str) -> Optional[Dict[str, Any]]:
        """Fetch an existing idempotency record by user, key, and endpoint."""
        rec = self.session.query(IdempotencyRecord).filter(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.key == key,
            IdempotencyRecord.endpoint == endpoint
        ).first()
        return _row_to_dict(rec) if rec else None

    def save_idempotency_record(self, user_id: int, key: str, endpoint: str, response_code: int, response_body: str) -> None:
        """Create and store a new idempotency response record."""
        rec = IdempotencyRecord(
            user_id=user_id,
            key=key,
            endpoint=endpoint,
            response_code=response_code,
            response_body=response_body
        )
        self.session.add(rec)
        self._commit()

    def create_notification(self, user_id: int, title: str, message: str, notif_type: str = "INFO") -> int:
        """Create a new in-app user notification."""
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notif_type,
            is_read=False
        )
        self.session.add(notif)
        self._commit()
        return notif.id

    def get_notifications(self, user_id: int) -> tuple[list[dict], int]:
        """Retrieve all notifications for a user in reverse chronological order along with unread_count."""
        records = (
            self.session.query(Notification)
            .filter(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .all()
        )
        notifications = [_row_to_dict(n) for n in records]
        unread_count = sum(1 for n in notifications if not n.get("is_read"))
        return notifications, unread_count

    def mark_notification_as_read(self, user_id: int, notification_id: int) -> bool:
        """Mark a specific notification as read for a given user."""
        notif = (
            self.session.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )
        if not notif:
            return False
        notif.is_read = True
        self._commit()
        return True

    def mark_all_notifications_as_read(self, user_id: int) -> None:
        """Mark all notifications as read for a given user."""
        self.session.query(Notification).filter(Notification.user_id == user_id, Notification.is_read == False).update(
            {Notification.is_read: True}, synchronize_session=False
        )
        self._commit()

    def close(self) -> None:
        """Close the database connection and dispose of engine if in pytest mode."""
        if self._session is not None:
            self._session.close()
            self._session = None
        if self._raw_conn is not None:
            self._raw_conn.close()
            self._raw_conn = None
            
        # For unit tests, we dispose the engine to release file locks on Windows
        is_pytest = (
            "TESTING" in os.environ 
            or "PYTEST_CURRENT_TEST" in os.environ
        )
        if is_pytest and hasattr(self, 'engine'):
            self.engine.dispose()
            global _engines_cache
            if self.db_url in _engines_cache:
                del _engines_cache[self.db_url]
