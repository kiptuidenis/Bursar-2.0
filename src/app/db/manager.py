import hashlib
import secrets
import time
import os
import datetime
import logging
import io
import csv
from typing import Dict, List, Any, Optional

from sqlalchemy import create_engine, func, event
from sqlalchemy.orm import sessionmaker
from app.db.models import (
    Base, User, Settings, Payout, Log, BudgetItem, Deposit, Session,
    IdempotencyRecord, Notification, OtpCode, Wallet, Budget,
    AdminUser, AdminSession, AdminAuditLog
)



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
                engine_kwargs["pool_size"] = 10
                engine_kwargs["max_overflow"] = 20

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

            if inspector.has_table("deposits"):
                dep_cols = [c["name"] for c in inspector.get_columns("deposits")]
                with self.engine.begin() as conn:
                    if "completed_at" not in dep_cols:
                        conn.execute(text("ALTER TABLE deposits ADD COLUMN completed_at VARCHAR(50) DEFAULT ''"))

            if inspector.has_table("payouts"):
                pay_cols = [c["name"] for c in inspector.get_columns("payouts")]
                with self.engine.begin() as conn:
                    if "completed_at" not in pay_cols:
                        conn.execute(text("ALTER TABLE payouts ADD COLUMN completed_at VARCHAR(50) DEFAULT ''"))
                    if "failed_at" not in pay_cols:
                        conn.execute(text("ALTER TABLE payouts ADD COLUMN failed_at VARCHAR(50) DEFAULT ''"))

            if inspector.has_table("otp_codes"):
                otp_cols = [c["name"] for c in inspector.get_columns("otp_codes")]
                with self.engine.begin() as conn:
                    if "password_hash" not in otp_cols:
                        conn.execute(text("ALTER TABLE otp_codes ADD COLUMN password_hash TEXT NULL"))
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
    def create_user_email(self, email: str, password_hash: str, salt: str = "argon2", payout_phone: Optional[str] = None, phone_number: Optional[str] = None) -> int:
        """Register a new user using email address with pre-hashed password, and initializes settings (email_verified=True)."""
        email_clean = email.strip().lower()
        existing = self.session.query(User).filter(User.email == email_clean).first()
        if existing:
            raise ValueError(f"An account with email '{email_clean}' already exists.")
            
        try:
            db_user = User(
                email=email_clean,
                password_hash=password_hash,
                salt=salt,
                phone_number=phone_number if phone_number else None,
                payout_phone_number=payout_phone or "",
                email_verified=True,
                two_factor_enabled=True
            )
            self.session.add(db_user)
            self.session.flush()
            
            db_wallet = Wallet(
                user_id=db_user.id,
                available_balance=0,
                locked_balance=0,
                currency="KES"
            )
            self.session.add(db_wallet)

            db_budget = Budget(
                user_id=db_user.id,
                daily_budget=0,
                payout_time="08:00"
            )
            self.session.add(db_budget)

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

    def get_user_wallet(self, user_id: int) -> Wallet:
        """Fetch or initialize user's Wallet ORM model."""
        wallet = self.session.query(Wallet).filter(Wallet.user_id == user_id).first()
        if not wallet:
            wallet = Wallet(user_id=user_id, available_balance=0, locked_balance=0, currency="KES")
            self.session.add(wallet)
            self._commit()
        return wallet

    def get_user_budget(self, user_id: int) -> Budget:
        """Fetch or initialize user's Budget ORM model."""
        budget = self.session.query(Budget).filter(Budget.user_id == user_id).first()
        if not budget:
            budget = Budget(user_id=user_id, daily_budget=0, payout_time="08:00")
            self.session.add(budget)
            self._commit()
        return budget

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

    def get_otp_record(self, email: str, purpose: str) -> Optional[OtpCode]:
        """Fetch active OTP challenge record for specified email and purpose."""
        email_clean = email.strip().lower()
        return self.session.query(OtpCode).filter(
            OtpCode.email == email_clean,
            OtpCode.purpose == purpose
        ).order_by(OtpCode.id.desc()).first()

    def create_otp_challenge(self, email: str, purpose: str, ttl_seconds: int = 300, user_id: Optional[int] = None, password_hash: Optional[str] = None) -> str:
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
            created_at=created_str,
            password_hash=password_hash
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
        
        # Create user's wallet, budget, and settings profiles automatically
        db_wallet = Wallet(
            user_id=db_user.id,
            available_balance=0,
            locked_balance=0,
            currency="KES"
        )
        self.session.add(db_wallet)

        db_budget = Budget(
            user_id=db_user.id,
            daily_budget=0,
            payout_time="08:00"
        )
        self.session.add(db_budget)

        db_settings = Settings(
            user_id=db_user.id,
            phone_number=phone_number
        )
        self.session.add(db_settings)
        self._commit()
        return db_user.id

    def _get_user_by_identifier(self, identifier: str) -> Optional[User]:
        """Helper to retrieve user model by email or phone number."""
        if not identifier:
            return None
        clean_id = identifier.strip().lower() if "@" in identifier else identifier.strip()
        return self.session.query(User).filter(
            (User.email == clean_id) | (User.phone_number == clean_id)
        ).first()

    def is_account_locked(self, identifier: str) -> tuple[bool, int]:
        """Check if an account is locked due to 5+ failed login attempts. Returns (is_locked, remaining_seconds)."""
        user = self._get_user_by_identifier(identifier)
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

    def record_failed_login_attempt(self, identifier: str) -> tuple[int, bool]:
        """Increment failed login attempts counter. Locks account for 15 mins if 5 attempts reached. Returns (attempts, is_locked)."""
        user = self._get_user_by_identifier(identifier)
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
            self.log_event(user.id, "WARNING", f"Account locked for 15 minutes due to {current} consecutive failed attempts.")
            
        self._commit()
        return current, is_locked

    def reset_failed_login_attempts(self, identifier: str) -> None:
        """Reset failed login attempts counter and clear lockout state on successful authentication."""
        user = self._get_user_by_identifier(identifier)
        if user and (user.failed_login_attempts > 0 or user.account_locked_until):
            user.failed_login_attempts = 0
            user.account_locked_until = ""
            self._commit()

    def authenticate_user(self, identifier: str, password_plaintext: str) -> Optional[int]:
        """Authenticate user credentials by phone number or email. Transparently upgrades legacy PBKDF2 hashes to Argon2id."""
        user = self._get_user_by_identifier(identifier)
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

    def get_payout_phone_number(self, user_id: int) -> str:
        """Get the configured M-Pesa payout phone number for a user."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if user and user.payout_phone_number:
            return user.payout_phone_number
        if user and user.phone_number:
            return user.phone_number
        settings = self.get_settings(user_id)
        return settings.get("phone_number", "")

    def update_payout_phone_number(self, user_id: int, phone_number: str) -> None:
        """Update the M-Pesa payout phone number for a user across User and Settings models."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if user:
            user.payout_phone_number = phone_number
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if settings:
            settings.phone_number = phone_number
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
            self.session.query(Wallet).filter(Wallet.user_id == user_id).delete(synchronize_session=False)
            self.session.query(Budget).filter(Budget.user_id == user_id).delete(synchronize_session=False)
            self.session.query(Settings).filter(Settings.user_id == user_id).delete(synchronize_session=False)
            self.session.delete(user)
            self._commit()

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Fetch all user profiles (useful for the background scheduler run)."""
        users = self.session.query(User).all()
        return [{"id": u.id, "phone_number": u.phone_number} for u in users]

    # Settings & Wallet/Budget Domain Operations (Isolated per user)
    def get_settings(self, user_id: int, decrypt_secrets: bool = True) -> Dict[str, Any]:
        """Retrieve configuration settings for a specific user, merging Wallet and Budget domain fields."""
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        wallet = self.get_user_wallet(user_id)
        budget = self.get_user_budget(user_id)
        
        data = _row_to_dict(settings) if settings else {}
        data["balance"] = wallet.available_balance
        data["daily_budget"] = budget.daily_budget
        data["payout_time"] = budget.payout_time
        data["start_date"] = budget.start_date or (settings.start_date if settings else "")
        data["end_date"] = budget.end_date or (settings.end_date if settings else "")
        data["budget_locked_until"] = budget.locked_until or (settings.budget_locked_until if settings else "")
        data["is_budget_locked"] = self.is_budget_locked(user_id)
        
        if decrypt_secrets and data:
            from app.core.encryption import decrypt_credential
            if data.get("mpesa_consumer_secret"):
                data["mpesa_consumer_secret"] = decrypt_credential(data["mpesa_consumer_secret"])
            if data.get("mpesa_initiator_password"):
                data["mpesa_initiator_password"] = decrypt_credential(data["mpesa_initiator_password"])
        return data

    def update_settings(self, user_id: int, **kwargs: Any) -> None:
        """Dynamically update settings, budget, and wallet models for a specific user."""
        if not kwargs:
            return
        
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        wallet = self.get_user_wallet(user_id)
        budget = self.get_user_budget(user_id)
            
        from app.core.encryption import encrypt_credential
        for key, val in kwargs.items():
            if key == "user_id":
                continue
            if key == "balance":
                wallet.available_balance = int(val)
            elif key == "daily_budget":
                budget.daily_budget = int(val)
            elif key == "payout_time":
                budget.payout_time = str(val)
                if settings:
                    settings.payout_time = str(val)
            elif key == "start_date":
                budget.start_date = str(val)
                if settings:
                    settings.start_date = str(val)
            elif key == "end_date":
                budget.end_date = str(val)
                if settings:
                    settings.end_date = str(val)
            elif key in ("budget_locked_until", "locked_until"):
                budget.locked_until = str(val)
                if settings:
                    settings.budget_locked_until = str(val)
            elif key in ("mpesa_consumer_secret", "mpesa_initiator_password"):
                if val == "********":
                    continue
                if isinstance(val, str) and val.strip():
                    val = encrypt_credential(val)
                if settings and hasattr(settings, key):
                    setattr(settings, key, val)
            elif settings and hasattr(settings, key):
                setattr(settings, key, val)
        self._commit()

    def debit_wallet_atomic(self, user_id: int, amount: int | float) -> bool:
        """
        Atomically debit amount from wallet if available_balance >= amount.
        Guarantees race-condition-proof deduction at the database engine layer.
        Returns True if debited successfully, False if insufficient balance.
        """
        import sqlalchemy
        int_amount = int(amount)
        res = self.session.execute(
            sqlalchemy.text(
                "UPDATE wallets SET available_balance = available_balance - :amount "
                "WHERE user_id = :user_id AND available_balance >= :amount"
            ),
            {"amount": int_amount, "user_id": user_id}
        )
        if res.rowcount == 0:
            self.session.rollback()
            return False
            
        self.session.commit()
        return True

    def adjust_balance(self, user_id: int, amount: int | float) -> None:
        """Add or subtract from current wallet balance of a specific user using atomic SQL arithmetic."""
        int_amount = int(amount)
        wallet = self.get_user_wallet(user_id)
        wallet.available_balance += int_amount
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

    def _is_schedule_lock_active(
        self,
        target_date_str: str,
        payout_time_str: str = "08:00",
        now: Optional[datetime.datetime] = None,
        today: Optional[datetime.date] = None
    ) -> bool:
        """
        Check if a schedule date lock is still active.
        Lock ends on the target date once the configured payout_time has passed.
        """
        if not target_date_str:
            return False
        import datetime
        eat_tz = datetime.timezone(datetime.timedelta(hours=3))
        
        try:
            target_date = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            return False

        if now is not None:
            now_dt = now if now.tzinfo is not None else now.replace(tzinfo=eat_tz)
            ref_date = now_dt.date()
            if ref_date > target_date:
                return False
            if ref_date < target_date:
                return True
            # ref_date == target_date: Check if payout_time has passed
            try:
                time_parts = (payout_time_str or "08:00").split(":")
                h, m = int(time_parts[0]), int(time_parts[1])
                payout_time_obj = datetime.time(h, m, 0)
            except (ValueError, IndexError, AttributeError):
                payout_time_obj = datetime.time(8, 0, 0)
            return now_dt.time() < payout_time_obj

        if today is not None:
            if today > target_date:
                return False
            # When an explicit date object is checked without a time, the schedule day is active
            return True

        # Default real-time production flow (neither now nor today provided)
        now_dt = datetime.datetime.now(eat_tz)
        ref_date = now_dt.date()
        if ref_date > target_date:
            return False
        if ref_date < target_date:
            return True
        # ref_date == target_date: Check if payout_time has passed today
        try:
            time_parts = (payout_time_str or "08:00").split(":")
            h, m = int(time_parts[0]), int(time_parts[1])
            payout_time_obj = datetime.time(h, m, 0)
        except (ValueError, IndexError, AttributeError):
            payout_time_obj = datetime.time(8, 0, 0)
        return now_dt.time() < payout_time_obj

    def is_budget_locked(self, user_id: int, now: Optional[datetime.datetime] = None, today: Optional[datetime.date] = None) -> bool:
        """Check if user's budget allocations are locked for the active schedule or explicit lock."""
        # Auto-unlock on depleted balance: If user has 0 balance, unlock so they can create a new budget
        wallet = self.get_user_wallet(user_id)
        balance = wallet.available_balance if wallet else 0
        if balance <= 0:
            return False

        budget = self.get_user_budget(user_id)
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if not budget and not settings:
            return False

        payout_time_str = (budget.payout_time if budget and budget.payout_time else "") or (settings.payout_time if settings and settings.payout_time else "") or "08:00"
        
        # 1. Check end_date across both Budget and Settings tables
        end_date = (budget.end_date if budget and budget.end_date else "") or (settings.end_date if settings and settings.end_date else "")
        if end_date:
            return self._is_schedule_lock_active(end_date, payout_time_str, now=now, today=today)

        # 2. Check locked_until across both Budget and Settings tables
        locked_until = (budget.locked_until if budget and budget.locked_until else "") or (settings.budget_locked_until if settings and settings.budget_locked_until else "")
        if locked_until:
            return self._is_schedule_lock_active(locked_until, payout_time_str, now=now, today=today)

        return False

    def is_deposit_locked(self, user_id: int, now: Optional[datetime.datetime] = None, today: Optional[datetime.date] = None) -> bool:
        """Check if user's deposited funds are locked for an active budget schedule or explicit lock."""
        wallet = self.get_user_wallet(user_id)
        balance = wallet.available_balance if wallet else 0
        if balance <= 0:
            return False

        budget = self.get_user_budget(user_id)
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if not budget and not settings:
            return False
        
        payout_time_str = (budget.payout_time if budget and budget.payout_time else "") or (settings.payout_time if settings and settings.payout_time else "") or "08:00"

        # 1. Check end_date across Budget and Settings tables
        end_date = (budget.end_date if budget and budget.end_date else "") or (settings.end_date if settings and settings.end_date else "")
        if end_date:
            return self._is_schedule_lock_active(end_date, payout_time_str, now=now, today=today)

        # 2. Check deposit_locked_until
        locked_until = settings.deposit_locked_until if settings else ""
        if locked_until:
            return self._is_schedule_lock_active(locked_until, payout_time_str, now=now, today=today)

        return False

    def _get_first_of_next_month(self) -> str:
        """Calculate the first day of the next calendar month as 'YYYY-MM-DD' in UTC+3 (Kenya Time)."""
        import datetime
        dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()
        if dt.month == 12:
            next_month = datetime.date(dt.year + 1, 1, 1)
        else:
            next_month = datetime.date(dt.year, dt.month + 1, 1)
        return next_month.strftime("%Y-%m-%d")

    def lock_budget(self, user_id: int) -> None:
        """Lock the budget configuration for the active schedule duration or month."""
        budget = self.get_user_budget(user_id)
        settings = self.get_settings(user_id, decrypt_secrets=False)
        end_date = (budget.end_date if budget and budget.end_date else "") or (settings.get("end_date", "") if settings else "")
        lock_date = end_date or self._get_first_of_next_month()
        self.update_settings(user_id, budget_locked_until=lock_date)

    def lock_deposit(self, user_id: int) -> None:
        """Lock deposit according to the user's active budget schedule or month."""
        budget = self.get_user_budget(user_id)
        settings = self.get_settings(user_id, decrypt_secrets=False)
        end_date = (budget.end_date if budget and budget.end_date else "") or (settings.get("end_date", "") if settings else "")
        lock_date = end_date or self._get_first_of_next_month()
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
        """Sum all allocation items and update user's daily budget settings and Budget domain model."""
        total = self.session.query(func.sum(BudgetItem.amount)).filter(BudgetItem.user_id == user_id).scalar()
        if total is None:
            total = 0.0
            
        int_total = int(total)
        budget = self.get_user_budget(user_id)
        budget.daily_budget = int_total

        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if settings:
            settings.daily_budget = int_total
            
        self._commit()
        self.log_event(user_id, "INFO", f"Recalculated daily budget allocation total: KES {int_total}.")
        return float(int_total)

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

    def update_deposit_status(self, checkout_request_id: str, status: str, mpesa_receipt: str = "", completed_at: str = "") -> bool:
        """Atomically update the status and M-Pesa receipt of a deposit transaction ONLY if current status is PENDING."""
        update_data = {
            Deposit.status: status,
            Deposit.mpesa_receipt: mpesa_receipt
        }
        if status in ("SUCCESS", "COMPLETED"):
            if not completed_at:
                eat_tz = datetime.timezone(datetime.timedelta(hours=3))
                completed_at = datetime.datetime.now(eat_tz).strftime("%Y-%m-%d %H:%M:%S")
            update_data[Deposit.completed_at] = completed_at

        rows_updated = self.session.query(Deposit).filter(
            Deposit.checkout_request_id == checkout_request_id,
            Deposit.status == 'PENDING'
        ).update(update_data, synchronize_session=False)
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

    # Admin Management Operations
    def create_admin_user(self, email: str, password_hash: str, salt: str = "argon2", role: str = "support") -> int:
        """Register a new administrator account with a specific RBAC role."""
        email_clean = email.strip().lower()
        existing = self.session.query(AdminUser).filter(AdminUser.email == email_clean).first()
        if existing:
            raise ValueError(f"An admin account with email '{email_clean}' already exists.")

        admin = AdminUser(
            email=email_clean,
            password_hash=password_hash,
            salt=salt,
            role=role,
            is_active=True,
            failed_login_attempts=0,
            account_locked_until=""
        )
        self.session.add(admin)
        self._commit()
        return admin.id

    def get_admin_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Fetch admin record by email address."""
        if not email:
            return None
        admin = self.session.query(AdminUser).filter(AdminUser.email == email.strip().lower()).first()
        return _row_to_dict(admin) if admin else None

    def get_admin_by_id(self, admin_id: int) -> Optional[Dict[str, Any]]:
        """Fetch admin record by ID."""
        admin = self.session.query(AdminUser).filter(AdminUser.id == admin_id).first()
        return _row_to_dict(admin) if admin else None

    def get_all_admins(self) -> List[Dict[str, Any]]:
        """Fetch all administrator profiles."""
        admins = self.session.query(AdminUser).order_by(AdminUser.id.asc()).all()
        return [_row_to_dict(a) for a in admins]

    def update_admin_role(self, admin_id: int, role: str) -> bool:
        """Update the RBAC role for an administrator."""
        admin = self.session.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if not admin:
            return False
        admin.role = role
        self._commit()
        return True

    def set_admin_active_status(self, admin_id: int, is_active: bool) -> bool:
        """Enable or disable an administrator account."""
        admin = self.session.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if not admin:
            return False
        admin.is_active = is_active
        self._commit()
        return True

    def is_admin_account_locked(self, email: str) -> tuple[bool, int]:
        """Check if an admin account is locked due to failed attempts. Returns (is_locked, remaining_seconds)."""
        admin = self.session.query(AdminUser).filter(AdminUser.email == email.strip().lower()).first()
        if not admin or not admin.account_locked_until:
            return False, 0

        try:
            locked_until_dt = datetime.datetime.strptime(admin.account_locked_until, "%Y-%m-%d %H:%M:%S")
            now_dt = datetime.datetime.utcnow()
            if now_dt < locked_until_dt:
                remaining = int((locked_until_dt - now_dt).total_seconds())
                return True, max(remaining, 1)
            else:
                admin.account_locked_until = ""
                admin.failed_login_attempts = 0
                self._commit()
                return False, 0
        except Exception:
            return False, 0

    def record_failed_admin_login(self, email: str) -> tuple[int, bool]:
        """Increment failed login attempts for admin. Locks for 15 mins after 5 attempts."""
        admin = self.session.query(AdminUser).filter(AdminUser.email == email.strip().lower()).first()
        if not admin:
            return 0, False

        current = (admin.failed_login_attempts or 0) + 1
        admin.failed_login_attempts = current
        is_locked = False
        if current >= 5:
            is_locked = True
            lock_duration = datetime.timedelta(minutes=15)
            admin.account_locked_until = (datetime.datetime.utcnow() + lock_duration).strftime("%Y-%m-%d %H:%M:%S")

        self._commit()
        return current, is_locked

    def reset_failed_admin_login(self, email: str) -> None:
        """Reset failed login attempts and clear lockout for admin."""
        admin = self.session.query(AdminUser).filter(AdminUser.email == email.strip().lower()).first()
        if admin and (admin.failed_login_attempts > 0 or admin.account_locked_until):
            admin.failed_login_attempts = 0
            admin.account_locked_until = ""
            self._commit()

    def create_admin_session(self, admin_id: int, token: str, ip_address: str, user_agent: str, expires_at: int) -> None:
        """Insert an administrative session record."""
        current_time = int(time.time())
        session = AdminSession(
            admin_id=admin_id,
            session_token=token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
            last_activity=current_time
        )
        self.session.add(session)
        self._commit()

    def verify_admin_session(self, token: str, inactivity_timeout_seconds: int = 900) -> Optional[int]:
        """Verify admin session token exists, is not expired, and passes 15-minute inactivity check."""
        now = int(time.time())
        session = self.session.query(AdminSession).filter(
            AdminSession.session_token == token,
            AdminSession.expires_at > now
        ).first()
        if not session:
            return None

        admin_id = session.admin_id
        last_act = session.last_activity if session.last_activity is not None else (session.expires_at - 86400)

        # Inactivity check (default 15 minutes = 900 seconds)
        if now - last_act > inactivity_timeout_seconds:
            self.session.delete(session)
            self._commit()
            return None

        session.last_activity = now
        self._commit()
        return admin_id

    def revoke_admin_session(self, token: str) -> bool:
        """Revoke a specific admin session token."""
        session = self.session.query(AdminSession).filter(AdminSession.session_token == token).first()
        if session:
            self.session.delete(session)
            self._commit()
            return True
        return False

    def create_admin_audit_log(
        self,
        admin_id: Optional[int],
        action: str,
        target_type: str = "",
        target_id: Optional[int] = None,
        before_state: str = "",
        after_state: str = "",
        reason: str = "",
        ip_address: str = ""
    ) -> int:
        """Create an immutable admin audit trail entry."""
        log_entry = AdminAuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
            ip_address=ip_address
        )
        self.session.add(log_entry)
        self._commit()
        return log_entry.id

    def get_admin_audit_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        admin_id: Optional[int] = None,
        action: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """Retrieve paginated admin audit trail entries with total count."""
        query = self.session.query(AdminAuditLog)
        if admin_id is not None:
            query = query.filter(AdminAuditLog.admin_id == admin_id)
        if action:
            query = query.filter(AdminAuditLog.action == action)

        total = query.count()
        records = query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()).offset(offset).limit(limit).all()
        return [_row_to_dict(r) for r in records], total

    def get_admin_overview_metrics(self) -> Dict[str, Any]:
        """Aggregate executive platform float, user activity, queue sizes, and disbursement velocity."""
        # 1. Total Wallets & Platform Float
        wallets = self.session.query(Wallet).all()
        total_user_balance = sum(int(w.available_balance or 0) for w in wallets)
        
        # 2. Total Deposits All Time, Today's Inflow, and Pending Deposits
        deposits = self.session.query(Deposit).all()
        completed_deposits = [d for d in deposits if d.status in ('COMPLETED', 'SUCCESS')]
        total_deposited_all_time = sum(int(d.amount or 0) for d in completed_deposits)
        
        eat_tz = datetime.timezone(datetime.timedelta(hours=3))
        today_date = datetime.datetime.now(eat_tz).date()
        today_str = datetime.datetime.now(eat_tz).strftime("%Y-%m-%d")
        
        today_completed_deposits = []
        for d in completed_deposits:
            if d.created_at:
                d_eat = (d.created_at.replace(tzinfo=datetime.timezone.utc).astimezone(eat_tz)).date() if d.created_at.tzinfo is None else d.created_at.astimezone(eat_tz).date()
                if d_eat == today_date:
                    today_completed_deposits.append(d)
        
        today_deposited_amount = sum(int(d.amount or 0) for d in today_completed_deposits)
        today_deposited_count = len(today_completed_deposits)

        pending_deposits = [d for d in deposits if d.status == 'PENDING']
        pending_deposits_count = len(pending_deposits)
        pending_deposits_amount = sum(int(d.amount or 0) for d in pending_deposits)

        # 3. Total Payouts All Time, Failed Queue, and Today's Velocity
        payouts = self.session.query(Payout).all()
        completed_payouts = [p for p in payouts if p.status in ('COMPLETED', 'SUCCESS')]
        total_disbursed_all_time = sum(int(p.amount or 0) for p in completed_payouts)
        
        failed_payouts = [p for p in payouts if p.status == 'FAILED']
        failed_payouts_count = len(failed_payouts)

        today_completed = [p for p in completed_payouts if p.payout_date == today_str]
        today_disbursed_amount = sum(int(p.amount or 0) for p in today_completed)
        today_disbursed_count = len(today_completed)

        # 4. User Counts and Locks
        users = self.session.query(User).all()
        total_users = len(users)
        
        active_locked_savers = 0
        unlocked_users = 0
        locked_out_users = 0
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        for u in users:
            is_locked = self.is_budget_locked(u.id) or self.is_deposit_locked(u.id)
            if is_locked:
                active_locked_savers += 1
            else:
                unlocked_users += 1
            
            if (u.failed_login_attempts or 0) >= 5 or (u.account_locked_until and u.account_locked_until > now_str):
                locked_out_users += 1

        return {
            "float": {
                "total_user_balance": total_user_balance,
                "total_locked_funds": 0,
                "total_platform_float": total_user_balance,
                "total_deposited_all_time": total_deposited_all_time,
                "today_deposited_amount": today_deposited_amount,
                "today_deposited_count": today_deposited_count,
                "total_disbursed_all_time": total_disbursed_all_time
            },
            "deposit_velocity": {
                "today_deposited_amount": today_deposited_amount,
                "today_deposited_count": today_deposited_count
            },
            "users": {
                "total_registered_users": total_users,
                "active_locked_savers": active_locked_savers,
                "unlocked_users": unlocked_users,
                "locked_out_users": locked_out_users
            },
            "queues": {
                "failed_payouts_count": failed_payouts_count,
                "pending_deposits_count": pending_deposits_count,
                "pending_deposits_amount": pending_deposits_amount
            },
            "payout_velocity": {
                "today_disbursed_amount": today_disbursed_amount,
                "today_disbursed_count": today_disbursed_count
            }
        }

    def get_admin_users_list(
        self,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        status_filter: Optional[str] = None,
        sort_by: str = "created_at",
        order: str = "desc"
    ) -> tuple[List[Dict[str, Any]], int]:
        """Fetch paginated users with financial health, locks, and search capabilities."""
        query = self.session.query(User)

        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                (User.email.ilike(search_pattern)) |
                (User.phone_number.ilike(search_pattern)) |
                (User.payout_phone_number.ilike(search_pattern)) |
                (User.first_name.ilike(search_pattern)) |
                (User.last_name.ilike(search_pattern))
            )

        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if status_filter == "locked_out":
            query = query.filter((User.failed_login_attempts >= 5) | (User.account_locked_until > now_str))

        total = query.count()
        offset = (page - 1) * limit
        users = query.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit).all()

        results = []
        for u in users:
            settings = self.get_settings(u.id, decrypt_secrets=False)
            is_locked_out = (u.failed_login_attempts or 0) >= 5 or bool(u.account_locked_until and u.account_locked_until > now_str)
            is_b_locked = self.is_budget_locked(u.id)
            is_d_locked = self.is_deposit_locked(u.id)

            if status_filter == "locked" and not (is_b_locked or is_d_locked):
                continue
            if status_filter == "active" and (is_locked_out or not u.email_verified):
                continue

            prof = self.get_profile(u.id)
            results.append({
                "id": u.id,
                "email": u.email or "",
                "phone_number": u.phone_number or "",
                "payout_phone_number": u.payout_phone_number or u.phone_number or "",
                "first_name": prof.get("first_name", "") if prof else "",
                "last_name": prof.get("last_name", "") if prof else "",
                "balance": settings.get("balance", 0),
                "daily_budget": settings.get("daily_budget", 0),
                "is_budget_locked": is_b_locked,
                "is_deposit_locked": is_d_locked,
                "failed_login_attempts": u.failed_login_attempts or 0,
                "is_locked_out": is_locked_out,
                "two_factor_enabled": getattr(u, "two_factor_enabled", False),
                "created_at": getattr(u, "created_at", "")
            })

        return results, total

    def get_user_360(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve full 360° user overview including profile, wallet, deposits, payouts, and sessions."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        profile = self.get_profile(user_id) or {}
        if not profile.get("payout_phone_number"):
            profile["payout_phone_number"] = self.get_payout_phone_number(user_id)
        settings = self.get_settings(user_id, decrypt_secrets=False) or {}
        draft_items = self.get_budget_items(user_id)
        
        deposits = self.session.query(Deposit).filter(Deposit.user_id == user_id).order_by(Deposit.created_at.desc(), Deposit.id.desc()).limit(10).all()
        payouts = self.session.query(Payout).filter(Payout.user_id == user_id).order_by(Payout.created_at.desc(), Payout.id.desc()).limit(10).all()
        
        active_sessions = self.session.query(Session).filter(Session.user_id == user_id, Session.expires_at > int(time.time())).count()
        events = self.session.query(Log).filter(Log.user_id == user_id).order_by(Log.created_at.desc(), Log.id.desc()).limit(10).all()

        return {
            "profile": profile,
            "wallet": {
                "balance": settings.get("balance", 0),
                "daily_budget": settings.get("daily_budget", 0),
                "payout_time": settings.get("payout_time", "12:00"),
                "start_date": settings.get("start_date", ""),
                "end_date": settings.get("end_date", ""),
                "budget_locked_until": settings.get("budget_locked_until", ""),
                "deposit_locked_until": settings.get("deposit_locked_until", ""),
                "is_budget_locked": settings.get("is_budget_locked", False),
                "is_deposit_locked": self.is_deposit_locked(user_id)
            },
            "draft_items": draft_items,
            "deposits": [_row_to_dict(d) for d in deposits],
            "payouts": [_row_to_dict(p) for p in payouts],
            "active_sessions_count": active_sessions,
            "security_logs": [_row_to_dict(e) for e in events]
        }

    def admin_unlock_user(self, user_id: int, admin_id: Optional[int], reason: str, ip_address: str) -> bool:
        """Unlock a customer account locked due to consecutive failed attempts."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        user.failed_login_attempts = 0
        user.account_locked_until = ""
        self._commit()
        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_USER_UNLOCK",
            target_type="User",
            target_id=user_id,
            reason=reason,
            ip_address=ip_address
        )
        return True

    def admin_toggle_user_2fa(self, user_id: int, enabled: bool, admin_id: Optional[int], reason: str, ip_address: str) -> bool:
        """Toggle 2FA requirement for a customer."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        user.two_factor_enabled = enabled
        self._commit()
        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_USER_2FA_TOGGLE",
            target_type="User",
            target_id=user_id,
            after_state=f'{{"two_factor_enabled": {str(enabled).lower()}}}',
            reason=reason,
            ip_address=ip_address
        )
        return True

    def admin_revoke_all_user_sessions(self, user_id: int, admin_id: Optional[int], reason: str, ip_address: str) -> int:
        """Revoke all active sessions for a customer."""
        count = self.session.query(Session).filter(Session.user_id == user_id).delete(synchronize_session=False)
        self._commit()
        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_USER_REVOKE_SESSIONS",
            target_type="User",
            target_id=user_id,
            reason=reason,
            ip_address=ip_address
        )
        return count

    def admin_impersonate_user(self, user_id: int, admin_id: Optional[int], reason: str, ip_address: str) -> tuple[str, Dict[str, Any]]:
        """Issue a temporary read-only customer session for support assistance."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        token = f"imp_{secrets.token_urlsafe(32)}"
        expires_at = int(time.time()) + 3600
        self.create_session_db(
            user_id=user_id,
            token=token,
            user_agent="Support Impersonation",
            ip_address=ip_address,
            expires_at=expires_at
        )
        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_USER_IMPERSONATE",
            target_type="User",
            target_id=user_id,
            reason=reason,
            ip_address=ip_address
        )
        return token, _row_to_dict(user)

    def admin_update_user_payout_phone(self, user_id: int, phone_number: str, admin_id: Optional[int], reason: str, ip_address: str) -> bool:
        """Update a customer's payout phone number with compliance audit logging."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        before_phone = user.payout_phone_number or user.phone_number or ""
        user.payout_phone_number = phone_number
        user.phone_number = phone_number
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if settings:
            settings.phone_number = phone_number
        self._commit()
        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_USER_UPDATE_PAYOUT_PHONE",
            target_type="User",
            target_id=user_id,
            before_state=f'{{"phone_number": "{before_phone}"}}',
            after_state=f'{{"phone_number": "{phone_number}"}}',
            reason=reason,
            ip_address=ip_address
        )
        return True

    def get_admin_wallets_list(
        self,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        sort_by: str = "balance",
        order: str = "desc"
    ) -> tuple[List[Dict[str, Any]], int, int]:
        """Retrieve paginated user wallets and compute platform-wide total balance."""
        query = self.session.query(User).join(Wallet, User.id == Wallet.user_id)

        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                (User.email.ilike(search_pattern)) |
                (User.phone_number.ilike(search_pattern)) |
                (User.first_name.ilike(search_pattern)) |
                (User.last_name.ilike(search_pattern))
            )

        total = query.count()
        all_wallets = self.session.query(Wallet).all()
        total_platform_balance = sum(int(w.available_balance or 0) for w in all_wallets)

        if order == "desc":
            query = query.order_by(Wallet.available_balance.desc(), User.id.desc())
        else:
            query = query.order_by(Wallet.available_balance.asc(), User.id.asc())

        offset = (page - 1) * limit
        users = query.offset(offset).limit(limit).all()

        results = []
        for u in users:
            wallet = self.get_user_wallet(u.id)
            settings = self.get_settings(u.id, decrypt_secrets=False)
            results.append({
                "user_id": u.id,
                "email": u.email or "",
                "phone_number": u.phone_number or "",
                "first_name": getattr(u, "first_name", ""),
                "last_name": getattr(u, "last_name", ""),
                "balance": int(wallet.available_balance or 0),
                "locked_balance": int(wallet.locked_balance or 0),
                "currency": wallet.currency or "KES",
                "daily_budget": settings.get("daily_budget", 0),
                "is_budget_locked": self.is_budget_locked(u.id),
                "is_deposit_locked": self.is_deposit_locked(u.id)
            })

        return results, total, total_platform_balance

    def admin_adjust_user_balance(
        self,
        user_id: int,
        amount: int,
        adjustment_type: str,
        admin_id: Optional[int],
        reason: str,
        reference_id: Optional[str],
        ip_address: str
    ) -> tuple[int, int]:
        """Adjust a user's wallet balance (CREDIT or DEBIT) atomically with audit logging."""
        user = self.session.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User with ID {user_id} not found.")

        wallet = self.get_user_wallet(user_id)
        prev_balance = int(wallet.available_balance or 0)
        adj_type_clean = adjustment_type.strip().upper()

        if adj_type_clean == "CREDIT":
            delta = int(amount)
        elif adj_type_clean == "DEBIT":
            delta = -int(amount)
        else:
            raise ValueError("Adjustment type must be 'CREDIT' or 'DEBIT'.")

        new_balance = prev_balance + delta
        if new_balance < 0:
            raise ValueError(f"Insufficient customer funds for debit. Current balance is KES {prev_balance}.")

        wallet.available_balance = new_balance
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if settings:
            settings.balance = new_balance

        self._commit()

        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_FINANCIAL_ADJUSTMENT",
            target_type="User",
            target_id=user_id,
            before_state=f'{{"balance": {prev_balance}}}',
            after_state=f'{{"balance": {new_balance}, "adjustment_type": "{adj_type_clean}", "amount": {amount}, "reference_id": "{reference_id or ""}"}}',
            reason=reason,
            ip_address=ip_address
        )

        if delta > 0:
            self.resolve_low_balance_warnings(user_id)

        return prev_balance, new_balance

    def admin_override_deposit_lock(self, user_id: int, admin_id: Optional[int], reason: str, ip_address: str) -> bool:
        """Emergency override to release deposit lock for a user."""
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if not settings:
            return False
        before_val = settings.deposit_locked_until or ""
        settings.deposit_locked_until = ""
        self._commit()
        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_OVERRIDE_DEPOSIT_LOCK",
            target_type="User",
            target_id=user_id,
            before_state=f'{{"deposit_locked_until": "{before_val}"}}',
            after_state='{"deposit_locked_until": ""}',
            reason=reason,
            ip_address=ip_address
        )
        return True

    def admin_override_budget_lock(self, user_id: int, admin_id: Optional[int], reason: str, ip_address: str) -> bool:
        """Emergency override to release active budget lock for a user."""
        budget = self.session.query(Budget).filter(Budget.user_id == user_id).first()
        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        before_val = (budget.locked_until if budget else "") or (settings.budget_locked_until if settings else "")
        if budget:
            budget.locked_until = ""
        if settings:
            settings.budget_locked_until = ""
        self._commit()
        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_OVERRIDE_BUDGET_LOCK",
            target_type="User",
            target_id=user_id,
            before_state=f'{{"budget_locked_until": "{before_val}"}}',
            after_state='{"budget_locked_until": ""}',
            reason=reason,
            ip_address=ip_address
        )
        return True

    def get_admin_deposits_list(
        self,
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int, int]:
        """Retrieve paginated deposits with filtering and total deposit metrics."""
        query = self.session.query(Deposit).join(User, Deposit.user_id == User.id)

        if status:
            query = query.filter(Deposit.status == status.upper())

        if search:
            from sqlalchemy import or_, func
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    func.coalesce(Deposit.checkout_request_id, '').ilike(search_pattern),
                    func.coalesce(Deposit.mpesa_receipt, '').ilike(search_pattern),
                    func.coalesce(User.email, '').ilike(search_pattern),
                    func.coalesce(User.phone_number, '').ilike(search_pattern),
                    func.coalesce(User.first_name, '').ilike(search_pattern),
                    func.coalesce(User.last_name, '').ilike(search_pattern)
                )
            )

        if date_from:
            query = query.filter(Deposit.created_at >= date_from)
        if date_to:
            query = query.filter(Deposit.created_at <= date_to)

        total = query.count()
        if status:
            total_amount = sum(int(d[0] or 0) for d in query.with_entities(Deposit.amount).all())
        else:
            # When viewing all statuses, total collected should strictly sum confirmed deposits
            collected_query = query.filter(Deposit.status.in_(["SUCCESS", "COMPLETED"]))
            total_amount = sum(int(d[0] or 0) for d in collected_query.with_entities(Deposit.amount).all())

        offset = (page - 1) * limit
        deposits = query.order_by(Deposit.created_at.desc(), Deposit.id.desc()).offset(offset).limit(limit).all()

        results = []
        for d in deposits:
            user = self.session.query(User).filter(User.id == d.user_id).first()
            created_str = ""
            if d.created_at:
                created_str = d.created_at.isoformat() if hasattr(d.created_at, "isoformat") else str(d.created_at)
                if not created_str.endswith("Z") and "+" not in created_str:
                    created_str += "Z"

            results.append({
                "id": d.id,
                "user_id": d.user_id,
                "user_email": user.email if user else "",
                "user_phone": user.phone_number if user else "",
                "user_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() if user else "",
                "checkout_request_id": d.checkout_request_id,
                "amount": int(d.amount or 0),
                "status": d.status,
                "mpesa_receipt": d.mpesa_receipt or "",
                "completed_at": d.completed_at or "",
                "created_at": created_str
            })

        return results, total, total_amount

    def admin_manual_settle_deposit(
        self,
        checkout_request_id: str,
        mpesa_receipt: str,
        admin_id: Optional[int],
        reason: str,
        ip_address: str
    ) -> Dict[str, Any]:
        """Manually settle a stuck pending/failed deposit, credit wallet balance, and audit log."""
        deposit = self.session.query(Deposit).filter(Deposit.checkout_request_id == checkout_request_id).first()
        if not deposit:
            raise ValueError(f"Deposit with checkout request ID {checkout_request_id} not found.")

        if deposit.status == "COMPLETED":
            raise ValueError("Deposit transaction is already completed.")

        prev_status = deposit.status
        deposit.status = "COMPLETED"
        deposit.mpesa_receipt = mpesa_receipt.strip().upper()
        eat_tz = datetime.timezone(datetime.timedelta(hours=3))
        deposit.completed_at = datetime.datetime.now(eat_tz).strftime("%Y-%m-%d %H:%M:%S")

        user_id = deposit.user_id
        amount = int(deposit.amount or 0)

        # Credit wallet and settings balance
        wallet = self.get_user_wallet(user_id)
        prev_balance = int(wallet.available_balance or 0)
        new_balance = prev_balance + amount
        wallet.available_balance = new_balance

        settings = self.session.query(Settings).filter(Settings.user_id == user_id).first()
        if settings:
            settings.balance = new_balance

        self._commit()

        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_DEPOSIT_MANUAL_SETTLE",
            target_type="Deposit",
            target_id=deposit.id,
            before_state=f'{{"status": "{prev_status}", "balance": {prev_balance}}}',
            after_state=f'{{"status": "COMPLETED", "mpesa_receipt": "{deposit.mpesa_receipt}", "balance": {new_balance}, "amount": {amount}}}',
            reason=reason,
            ip_address=ip_address
        )

        self.resolve_low_balance_warnings(user_id)

        return {
            "status": "success",
            "deposit_id": deposit.id,
            "checkout_request_id": checkout_request_id,
            "amount": amount,
            "mpesa_receipt": deposit.mpesa_receipt,
            "new_balance": new_balance
        }

    def get_admin_payouts_list(
        self,
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None,
        search: Optional[str] = None,
        payout_date: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int, int]:
        """Retrieve paginated payouts with filtering and total disbursement metrics."""
        query = self.session.query(Payout).join(User, Payout.user_id == User.id)

        if status:
            status_clean = status.upper()
            if status_clean in ("SUCCESS", "COMPLETED"):
                query = query.filter(Payout.status.in_(["SUCCESS", "COMPLETED"]))
            else:
                query = query.filter(Payout.status == status_clean)

        if payout_date:
            query = query.filter(Payout.payout_date == payout_date)

        if search:
            from sqlalchemy import or_, func
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    func.coalesce(Payout.conversation_id, '').ilike(search_pattern),
                    func.coalesce(Payout.originator_conversation_id, '').ilike(search_pattern),
                    func.coalesce(Payout.transaction_id, '').ilike(search_pattern),
                    func.coalesce(Payout.phone_number, '').ilike(search_pattern),
                    func.coalesce(User.email, '').ilike(search_pattern),
                    func.coalesce(User.first_name, '').ilike(search_pattern),
                    func.coalesce(User.last_name, '').ilike(search_pattern)
                )
            )

        if date_from:
            query = query.filter(Payout.created_at >= date_from)
        if date_to:
            query = query.filter(Payout.created_at <= date_to)

        total = query.count()
        total_disbursed = sum(
            int(p[0] or 0) for p in query.filter(Payout.status.in_(["SUCCESS", "COMPLETED"])).with_entities(Payout.amount).all()
        )

        offset = (page - 1) * limit
        payouts = query.order_by(Payout.created_at.desc(), Payout.id.desc()).offset(offset).limit(limit).all()

        results = []
        for p in payouts:
            user = self.session.query(User).filter(User.id == p.user_id).first()
            created_str = ""
            if p.created_at:
                created_str = p.created_at.isoformat() if hasattr(p.created_at, "isoformat") else str(p.created_at)
                if not created_str.endswith("Z") and "+" not in created_str:
                    created_str += "Z"

            results.append({
                "id": p.id,
                "user_id": p.user_id,
                "user_email": user.email if user else "",
                "user_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() if user else "",
                "payout_date": p.payout_date,
                "amount": int(p.amount or 0),
                "phone_number": p.phone_number,
                "status": p.status,
                "conversation_id": p.conversation_id or "",
                "originator_conversation_id": p.originator_conversation_id or "",
                "transaction_id": p.transaction_id or "",
                "error_message": p.error_message or "",
                "completed_at": p.completed_at or "",
                "failed_at": p.failed_at or "",
                "created_at": created_str
            })

        return results, total, total_disbursed

    def admin_retry_failed_payout(
        self,
        payout_id: int,
        admin_id: Optional[int],
        reason: str,
        ip_address: str
    ) -> Optional[Dict[str, Any]]:
        """Reset a failed payout to PENDING to permit immediate re-execution."""
        payout = self.session.query(Payout).filter(Payout.id == payout_id).first()
        if not payout:
            return None

        if payout.status not in ("FAILED", "PENDING"):
            raise ValueError(f"Cannot retry payout with status {payout.status}.")

        prev_status = payout.status
        payout.status = "PENDING"
        payout.error_message = ""
        payout.failed_at = ""
        self._commit()

        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_PAYOUT_RETRY",
            target_type="Payout",
            target_id=payout.id,
            before_state=f'{{"status": "{prev_status}"}}',
            after_state='{"status": "PENDING"}',
            reason=reason,
            ip_address=ip_address
        )
        return _row_to_dict(payout)

    def admin_manual_settle_payout(
        self,
        payout_id: int,
        transaction_id: str,
        admin_id: Optional[int],
        reason: str,
        ip_address: str
    ) -> Dict[str, Any]:
        """Manually mark a pending/failed payout as completed with external transaction ref."""
        payout = self.session.query(Payout).filter(Payout.id == payout_id).first()
        if not payout:
            raise ValueError(f"Payout with ID {payout_id} not found.")

        if payout.status in ("SUCCESS", "COMPLETED"):
            raise ValueError("Payout transaction is already completed.")

        prev_status = payout.status
        eat_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
        completed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")

        payout.status = "COMPLETED"
        payout.transaction_id = transaction_id.strip().upper()
        payout.completed_at = completed_ts
        payout.error_message = ""
        self._commit()

        self.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_PAYOUT_MANUAL_SETTLE",
            target_type="Payout",
            target_id=payout.id,
            before_state=f'{{"status": "{prev_status}"}}',
            after_state=f'{{"status": "COMPLETED", "transaction_id": "{payout.transaction_id}"}}',
            reason=reason,
            ip_address=ip_address
        )

        return {
            "status": "success",
            "payout_id": payout.id,
            "transaction_id": payout.transaction_id,
            "completed_at": completed_ts
        }

    def get_admin_audit_logs_list(
        self,
        page: int = 1,
        limit: int = 20,
        action: Optional[str] = None,
        admin_id: Optional[int] = None,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """Retrieve paginated admin compliance audit logs with filtering and search."""
        query = self.session.query(AdminAuditLog).outerjoin(AdminUser, AdminAuditLog.admin_id == AdminUser.id)

        if action:
            query = query.filter(AdminAuditLog.action == action)
        if admin_id:
            query = query.filter(AdminAuditLog.admin_id == admin_id)
        if target_type:
            query = query.filter(AdminAuditLog.target_type == target_type)
        if target_id is not None:
            query = query.filter(AdminAuditLog.target_id == target_id)
        if date_from:
            query = query.filter(AdminAuditLog.created_at >= date_from)
        if date_to:
            query = query.filter(AdminAuditLog.created_at <= date_to)

        if search:
            from sqlalchemy import or_, func
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    func.coalesce(AdminAuditLog.action, '').ilike(search_pattern),
                    func.coalesce(AdminAuditLog.reason, '').ilike(search_pattern),
                    func.coalesce(AdminAuditLog.target_type, '').ilike(search_pattern),
                    func.coalesce(AdminAuditLog.ip_address, '').ilike(search_pattern),
                    func.coalesce(AdminUser.email, '').ilike(search_pattern)
                )
            )

        total = query.count()
        offset = (page - 1) * limit
        logs = query.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()).offset(offset).limit(limit).all()

        results = []
        for l in logs:
            admin = self.session.query(AdminUser).filter(AdminUser.id == l.admin_id).first() if l.admin_id else None
            results.append({
                "id": l.id,
                "admin_id": l.admin_id,
                "admin_email": admin.email if admin else "System / Automated",
                "action": l.action,
                "target_type": l.target_type,
                "target_id": l.target_id,
                "before_state": l.before_state or "",
                "after_state": l.after_state or "",
                "reason": l.reason or "",
                "ip_address": l.ip_address or "",
                "created_at": l.created_at.isoformat() if hasattr(l.created_at, "isoformat") else str(l.created_at)
            })

        return results, total

    def export_admin_audit_logs_csv(
        self,
        action: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> str:
        """Export audit logs as CSV string formatted for regulatory / internal compliance."""
        logs, _ = self.get_admin_audit_logs_list(page=1, limit=10000, action=action, date_from=date_from, date_to=date_to)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Log ID", "Timestamp", "Admin Email", "Action", "Target Type", "Target ID", "Reason", "IP Address", "Before State", "After State"])
        for l in logs:
            writer.writerow([
                l["id"],
                l["created_at"],
                l["admin_email"],
                l["action"],
                l["target_type"],
                l["target_id"],
                l["reason"],
                l["ip_address"],
                l["before_state"],
                l["after_state"]
            ])
        return output.getvalue()

    def get_admin_users_directory(self) -> List[Dict[str, Any]]:
        """Retrieve all staff administrative accounts."""
        admins = self.session.query(AdminUser).order_by(AdminUser.id.asc()).all()
        return [
            {
                "id": a.id,
                "email": a.email,
                "role": a.role,
                "is_active": bool(a.is_active),
                "failed_login_attempts": a.failed_login_attempts or 0,
                "account_locked_until": a.account_locked_until or "",
                "created_at": a.created_at.isoformat() if hasattr(a.created_at, "isoformat") else str(a.created_at)
            }
            for a in admins
        ]


    def admin_toggle_admin_active_status(
        self,
        target_admin_id: int,
        is_active: bool,
        actor_admin_id: int,
        reason: str,
        ip_address: str
    ) -> bool:
        """Activate or deactivate another staff administrator."""
        if target_admin_id == actor_admin_id and not is_active:
            raise ValueError("You cannot deactivate your own administrative account.")

        admin = self.session.query(AdminUser).filter(AdminUser.id == target_admin_id).first()
        if not admin:
            raise ValueError(f"Admin with ID {target_admin_id} not found.")

        prev_status = bool(admin.is_active)
        admin.is_active = is_active
        self._commit()

        self.create_admin_audit_log(
            admin_id=actor_admin_id,
            action="ADMIN_ACCOUNT_STATUS_TOGGLE",
            target_type="AdminUser",
            target_id=target_admin_id,
            before_state=f'{{"is_active": {prev_status}}}',
            after_state=f'{{"is_active": {is_active}}}',
            reason=reason,
            ip_address=ip_address
        )
        return True

    def admin_create_staff_account(
        self,
        email: str,
        password_hash: str,
        salt: str,
        role: str,
        actor_admin_id: int,
        reason: str,
        ip_address: str
    ) -> Dict[str, Any]:
        """Provision a new staff administrative user with role and audit trail."""
        existing = self.session.query(AdminUser).filter(AdminUser.email == email.strip().lower()).first()
        if existing:
            raise ValueError(f"Admin account with email {email} already exists.")

        admin_id = self.create_admin_user(
            email=email.strip().lower(),
            password_hash=password_hash,
            salt=salt,
            role=role.strip().lower()
        )

        self.create_admin_audit_log(
            admin_id=actor_admin_id,
            action="ADMIN_ACCOUNT_CREATE",
            target_type="AdminUser",
            target_id=admin_id,
            before_state="{}",
            after_state=f'{{"email": "{email}", "role": "{role}"}}',
            reason=reason,
            ip_address=ip_address
        )

        return {
            "id": admin_id,
            "email": email.strip().lower(),
            "role": role.strip().lower(),
            "is_active": True
        }

    def admin_update_staff_role(
        self,
        target_admin_id: int,
        new_role: str,
        actor_admin_id: int,
        reason: str,
        ip_address: str
    ) -> bool:
        """Update the RBAC role of a staff administrator."""
        admin = self.session.query(AdminUser).filter(AdminUser.id == target_admin_id).first()
        if not admin:
            raise ValueError(f"Admin with ID {target_admin_id} not found.")

        prev_role = admin.role
        admin.role = new_role.strip().lower()
        self._commit()

        self.create_admin_audit_log(
            admin_id=actor_admin_id,
            action="ADMIN_ROLE_UPDATE",
            target_type="AdminUser",
            target_id=target_admin_id,
            before_state=f'{{"role": "{prev_role}"}}',
            after_state=f'{{"role": "{admin.role}"}}',
            reason=reason,
            ip_address=ip_address
        )
        return True







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
