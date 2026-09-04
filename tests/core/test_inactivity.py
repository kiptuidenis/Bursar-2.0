import time
import pytest
from app.db.manager import DatabaseManager
from app.core.security import SessionManager

@pytest.fixture
def db():
    # Use a temporary SQLite database for testing
    db_file = "test_inactivity.db"
    manager = DatabaseManager(db_file)
    manager.initialize()
    yield manager
    manager.close()
    import os
    if os.path.exists(db_file):
        os.remove(db_file)

@pytest.fixture
def security_manager():
    return SessionManager(secret_key="test_secret_key_inactivity_32_chars_len")


def test_session_inactivity_expiry(db, security_manager):
    user_id = db.create_user("254711111111", "1234")
    token = security_manager.create_session(user_id, expires_in_seconds=3600, db=db)
    
    # Session should be valid initially
    assert db.verify_session_token_db(token) == user_id
    
    # Manually modify last_activity in the DB to be 31 minutes ago (1860 seconds ago)
    conn = db.connection
    cursor = conn.cursor()
    past_time = int(time.time()) - 1860
    cursor.execute("UPDATE sessions SET last_activity = ? WHERE session_token = ?", (past_time, token))
    conn.commit()
    
    # Session verification should fail now (inactivity check triggered)
    assert db.verify_session_token_db(token) is None

def test_session_activity_update(db, security_manager):
    user_id = db.create_user("254722222222", "1234")
    token = security_manager.create_session(user_id, expires_in_seconds=3600, db=db)
    
    # Manually set last_activity to 1 minute ago (within 5-minute inactivity window)
    conn = db.connection
    cursor = conn.cursor()
    past_time = int(time.time()) - 60
    cursor.execute("UPDATE sessions SET last_activity = ? WHERE session_token = ?", (past_time, token))
    conn.commit()
    
    # Verify with is_poll=True -> should NOT update last_activity
    assert db.verify_session_token_db(token, is_poll=True) == user_id
    cursor.execute("SELECT last_activity FROM sessions WHERE session_token = ?", (token,))
    assert cursor.fetchone()["last_activity"] == past_time
    
    # Verify with is_poll=False -> should update last_activity to now
    assert db.verify_session_token_db(token, is_poll=False) == user_id
    cursor.execute("SELECT last_activity FROM sessions WHERE session_token = ?", (token,))
    updated_time = cursor.fetchone()["last_activity"]
    assert updated_time > past_time
    assert abs(updated_time - int(time.time())) <= 5

def test_session_cleanup(db, security_manager):
    user_id = db.create_user("254733333333", "1234")
    token1 = security_manager.create_session(user_id, expires_in_seconds=3600, db=db)
    token2 = security_manager.create_session(user_id, expires_in_seconds=3600, db=db)
    
    # Manually set last_activity for token1 to 31 minutes ago
    conn = db.connection
    cursor = conn.cursor()
    past_time = int(time.time()) - 1860
    cursor.execute("UPDATE sessions SET last_activity = ? WHERE session_token = ?", (past_time, token1))
    conn.commit()
    
    # Run cleanup
    db.cleanup_expired_sessions(inactivity_timeout_seconds=1800)
    
    # Verify token1 is deleted, but token2 remains active
    cursor.execute("SELECT COUNT(*) as cnt FROM sessions WHERE session_token = ?", (token1,))
    assert cursor.fetchone()["cnt"] == 0
    
    cursor.execute("SELECT COUNT(*) as cnt FROM sessions WHERE session_token = ?", (token2,))
    assert cursor.fetchone()["cnt"] == 1
