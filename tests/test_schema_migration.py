import os
import sqlite3
import pytest
from app.db.manager import DatabaseManager

TEST_OLD_DB = "test_old_schema.db"

@pytest.fixture
def old_schema_db():
    if os.path.exists(TEST_OLD_DB):
        try:
            os.remove(TEST_OLD_DB)
        except OSError:
            pass

    # Create an old schema SQLite database WITHOUT failed_login_attempts & account_locked_until
    conn = sqlite3.connect(TEST_OLD_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            salt VARCHAR(255) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            first_name VARCHAR(100) DEFAULT '',
            last_name VARCHAR(100) DEFAULT '',
            email VARCHAR(100) DEFAULT '',
            avatar_url VARCHAR(255) DEFAULT '',
            bio VARCHAR(500) DEFAULT '',
            theme VARCHAR(50) DEFAULT '',
            notifications_enabled INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

    yield TEST_OLD_DB

    if os.path.exists(TEST_OLD_DB):
        try:
            os.remove(TEST_OLD_DB)
        except OSError:
            pass


def test_auto_migration_adds_missing_columns_to_existing_database(old_schema_db):
    """
    Verifies that initializing DatabaseManager on a pre-existing production database (MySQL/SQLite)
    without new columns automatically executes ALTER TABLE to add missing columns without errors.
    """
    manager = DatabaseManager(old_schema_db)
    # Run initialize() which executes _auto_migrate_columns()
    manager.initialize()

    try:
        # Verify columns now exist by inspecting table or creating/authenticating a user
        user_id = manager.create_user("254700999000", "testpassword")
        assert user_id is not None

        # Record a failed login attempt to verify SQL queries on failed_login_attempts column work cleanly
        attempts, is_locked = manager.record_failed_login_attempt("254700999000")
        assert attempts == 1
        assert is_locked is False

    finally:
        manager.close()
