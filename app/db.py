import sqlite3
import hashlib
import secrets
from typing import Dict, List, Any, Optional

class DatabaseManager:
    def __init__(self, db_path: str = "bursar.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Initialize the database schema for multi-tenancy."""
        conn = self.connection
        cursor = conn.cursor()
        
        # Detect legacy single-user schema and recreate tables if necessary
        cursor.execute("PRAGMA table_info(logs)")
        columns = [row["name"] for row in cursor.fetchall()]
        if columns and "user_id" not in columns:
            cursor.execute("DROP TABLE IF EXISTS logs")
            cursor.execute("DROP TABLE IF EXISTS payouts")
            cursor.execute("DROP TABLE IF EXISTS settings")
            cursor.execute("DROP TABLE IF EXISTS users")
            conn.commit()
            
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create settings table (keyed by user_id)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                daily_budget REAL DEFAULT 0.0,
                phone_number TEXT DEFAULT '',
                payout_time TEXT DEFAULT '08:00',
                mode TEXT DEFAULT 'sandbox',
                mpesa_consumer_key TEXT DEFAULT '',
                mpesa_consumer_secret TEXT DEFAULT '',
                mpesa_shortcode TEXT DEFAULT '',
                mpesa_initiator_name TEXT DEFAULT '',
                mpesa_initiator_password TEXT DEFAULT '',
                mpesa_b2c_result_url TEXT DEFAULT '',
                mpesa_b2c_timeout_url TEXT DEFAULT '',
                budget_locked_until TEXT DEFAULT '',
                deposit_locked_until TEXT DEFAULT '',
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create payouts table with composite uniqueness constraint (user_id + payout_date)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                payout_date TEXT NOT NULL,
                amount REAL NOT NULL,
                phone_number TEXT NOT NULL,
                status TEXT NOT NULL,
                conversation_id TEXT DEFAULT '',
                originator_conversation_id TEXT DEFAULT '',
                transaction_id TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE (user_id, payout_date)
            )
        """)
        
        # Create system logs table per user
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create budget items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE (user_id, category)
            )
        """)
        
        # Add dynamic locking columns to settings if they do not exist
        cursor.execute("PRAGMA table_info(settings)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "budget_locked_until" not in columns:
            cursor.execute("ALTER TABLE settings ADD COLUMN budget_locked_until TEXT DEFAULT ''")
        if "deposit_locked_until" not in columns:
            cursor.execute("ALTER TABLE settings ADD COLUMN deposit_locked_until TEXT DEFAULT ''")
        if "start_date" not in columns:
            cursor.execute("ALTER TABLE settings ADD COLUMN start_date TEXT DEFAULT ''")
        if "end_date" not in columns:
            cursor.execute("ALTER TABLE settings ADD COLUMN end_date TEXT DEFAULT ''")
            
        # Migrate any legacy 'simulation' modes to 'sandbox'
        cursor.execute("UPDATE settings SET mode = 'sandbox' WHERE mode = 'simulation'")
            
        conn.commit()

    # Cryptographic Hashing Helpers
    def _hash_password(self, password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """Hash a plaintext password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
        if salt is None:
            salt = secrets.token_bytes(16)
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            100000
        )
        return hash_bytes.hex(), salt.hex()

    def _verify_password(self, password: str, password_hash_hex: str, salt_hex: str) -> bool:
        """Verify password against stored hash."""
        salt = bytes.fromhex(salt_hex)
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            100000
        )
        return hash_bytes.hex() == password_hash_hex

    # User Auth Operations
    def create_user(self, phone_number: str, password_plaintext: str) -> int:
        """Register a new user, hashes password, and creates default settings row."""
        conn = self.connection
        cursor = conn.cursor()
        
        password_hash, salt = self._hash_password(password_plaintext)
        
        cursor.execute("""
            INSERT INTO users (phone_number, password_hash, salt)
            VALUES (?, ?, ?)
        """, (phone_number, password_hash, salt))
        
        user_id = cursor.lastrowid
        
        # Create user's settings profile automatically (defaulting settings phone number to registration phone number)
        cursor.execute("""
            INSERT INTO settings (user_id, phone_number)
            VALUES (?, ?)
        """, (user_id, phone_number))
        
        conn.commit()
        return user_id

    def authenticate_user(self, phone_number: str, password_plaintext: str) -> Optional[int]:
        """Authenticate user credentials. Returns user_id if valid, None otherwise."""
        conn = self.connection
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, password_hash, salt FROM users WHERE phone_number = ?", (phone_number,))
        row = cursor.fetchone()
        if not row:
            return None
            
        user_id = row["id"]
        stored_hash = row["password_hash"]
        stored_salt = row["salt"]
        
        if self._verify_password(password_plaintext, stored_hash, stored_salt):
            return user_id
        return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Fetch all user profiles (useful for the background scheduler run)."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("SELECT id, phone_number FROM users")
        return [dict(row) for row in cursor.fetchall()]

    # Settings Operations (Isolated per user)
    def get_settings(self, user_id: int) -> Dict[str, Any]:
        """Retrieve the configuration settings for a specific user."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}

    def update_settings(self, user_id: int, **kwargs: Any) -> None:
        """Dynamically update settings columns for a specific user."""
        if not kwargs:
            return
        
        conn = self.connection
        cursor = conn.cursor()
        
        fields = []
        values = []
        for key, val in kwargs.items():
            # Filter out user_id updates
            if key == "user_id":
                continue
            fields.append(f"{key} = ?")
            values.append(val)
            
        values.append(user_id)
        query = f"UPDATE settings SET {', '.join(fields)} WHERE user_id = ?"
        cursor.execute(query, values)
        conn.commit()

    def adjust_balance(self, user_id: int, amount: float) -> None:
        """Add or subtract from the current wallet balance of a specific user."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

    def is_budget_locked(self, user_id: int) -> bool:
        """Check if the user's budget allocations are locked for the current calendar month."""
        settings = self.get_settings(user_id)
        if not settings:
            return False
        locked_until = settings.get("budget_locked_until", "")
        if not locked_until:
            return False
        import datetime
        try:
            lock_date = datetime.datetime.strptime(locked_until, "%Y-%m-%d").date()
            return datetime.date.today() < lock_date
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
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payouts (user_id, payout_date, amount, phone_number, status, conversation_id, originator_conversation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, payout_date, amount, phone_number, status, conversation_id, originator_conversation_id))
        conn.commit()
        return cursor.lastrowid

    def update_payout_status(self, conversation_id: str, status: str, 
                             transaction_id: str = "", error_message: str = "") -> None:
        """Update payout record status by ConversationID (called by global webhook)."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE payouts 
            SET status = ?, transaction_id = ?, error_message = ? 
            WHERE conversation_id = ?
        """, (status, transaction_id, error_message, conversation_id))
        conn.commit()

    def get_payout_by_conversation_id(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific payout transaction by conversation ID across all users."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payouts WHERE conversation_id = ?", (conversation_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_payouts(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch past payouts for a specific user, sorted by created_at DESC, id DESC."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payouts WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?", (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]

    # Logging Operations (Isolated per user)
    def log_event(self, user_id: int, level: str, message: str) -> None:
        """Write a system event to logs for a specific user."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("INSERT INTO logs (user_id, level, message) VALUES (?, ?, ?)", (user_id, level, message))
        conn.commit()

    def get_logs(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch system logs for a specific user, sorted by id DESC."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM logs WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_budget_items(self, user_id: int) -> List[Dict[str, Any]]:
        """Fetch all budget allocation items for a specific user."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM budget_items WHERE user_id = ? ORDER BY category ASC", (user_id,))
        return [dict(row) for row in cursor.fetchall()]

    def add_or_update_budget_item(self, user_id: int, category: str, amount: float) -> int:
        """Add a new budget allocation item or update it if the category already exists."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO budget_items (user_id, category, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, category) DO UPDATE SET amount = excluded.amount
        """, (user_id, category, amount))
        conn.commit()
        item_id = cursor.lastrowid
        self.recalculate_daily_budget(user_id)
        return item_id

    def delete_budget_item(self, user_id: int, item_id: int) -> bool:
        """Delete a specific budget allocation item for a user."""
        conn = self.connection
        cursor = conn.cursor()
        cursor.execute("DELETE FROM budget_items WHERE user_id = ? AND id = ?", (user_id, item_id))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            self.recalculate_daily_budget(user_id)
        return deleted

    def recalculate_daily_budget(self, user_id: int) -> float:
        """Sum all allocation items and update the user's daily budget settings."""
        conn = self.connection
        cursor = conn.cursor()
        
        # Calculate sum
        cursor.execute("SELECT SUM(amount) as total FROM budget_items WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        total = row["total"] if row and row["total"] is not None else 0.0
        
        # Update settings table
        cursor.execute("UPDATE settings SET daily_budget = ? WHERE user_id = ?", (total, user_id))
        conn.commit()
        
        self.log_event(user_id, "INFO", f"Recalculated daily budget allocation total: KES {total:.2f}.")
        return total

    def close(self) -> None:
        """Close the sqlite database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
