import os
import pytest
import sqlite3
from app.db import DatabaseManager

DB_FILE = "test_bursar_multitenant.db"

@pytest.fixture
def db():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    
    manager = DatabaseManager(DB_FILE)
    manager.initialize()
    yield manager
    
    manager.close()
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

def test_user_registration_and_auth(db):
    # Register first user
    user1_id = db.create_user("254712345678", "securepin123")
    assert user1_id is not None
    
    # Try duplicate registration (must raise sqlite3.IntegrityError)
    with pytest.raises(sqlite3.IntegrityError):
        db.create_user("254712345678", "anotherpassword")
        
    # Register second user
    user2_id = db.create_user("254711223344", "pypassword")
    assert user2_id is not None
    assert user1_id != user2_id
    
    # Authenticate successfully
    auth_user1 = db.authenticate_user("254712345678", "securepin123")
    assert auth_user1 == user1_id
    
    # Authenticate with incorrect password (should return None)
    auth_fail = db.authenticate_user("254712345678", "wrongpass")
    assert auth_fail is None
    
    # Authenticate non-existent user (should return None)
    auth_none = db.authenticate_user("254700000000", "pass")
    assert auth_none is None

def test_settings_isolation(db):
    user1_id = db.create_user("254712345678", "pass1")
    user2_id = db.create_user("254711223344", "pass2")
    
    # Verify default settings are created for both users
    settings1 = db.get_settings(user1_id)
    settings2 = db.get_settings(user2_id)
    assert settings1["balance"] == 0.0
    assert settings2["balance"] == 0.0
    
    # Update settings for user 1
    db.update_settings(user1_id, balance=3500.0, daily_budget=150.0, mode="sandbox")
    
    # Verify settings updated for user 1, but user 2 remains unchanged
    s1 = db.get_settings(user1_id)
    s2 = db.get_settings(user2_id)
    assert s1["balance"] == 3500.0
    assert s1["daily_budget"] == 150.0
    assert s1["mode"] == "sandbox"
    
    assert s2["balance"] == 0.0
    assert s2["daily_budget"] == 0.0
    assert s2["mode"] == "simulation"

def test_balance_adjustment_isolation(db):
    user1_id = db.create_user("254712345678", "pass1")
    user2_id = db.create_user("254711223344", "pass2")
    
    db.update_settings(user1_id, balance=1000.0)
    db.update_settings(user2_id, balance=500.0)
    
    # Adjust balance for user 1
    db.adjust_balance(user1_id, -200.0)
    
    # Verify isolation
    assert db.get_settings(user1_id)["balance"] == 800.0
    assert db.get_settings(user2_id)["balance"] == 500.0

def test_payout_creation_and_composite_idempotency(db):
    user1_id = db.create_user("254712345678", "pass1")
    user2_id = db.create_user("254711223344", "pass2")
    
    # User 1 makes a payout for date 2026-06-18
    p1 = db.create_payout(user1_id, "2026-06-18", 100.0, "254712345678", "SUCCESS", "conv1")
    assert p1 is not None
    
    # User 2 makes a payout for the same date 2026-06-18 (should succeed due to composite constraint)
    p2 = db.create_payout(user2_id, "2026-06-18", 150.0, "254711223344", "SUCCESS", "conv2")
    assert p2 is not None
    
    # User 1 attempts a second payout for date 2026-06-18 (should raise IntegrityError - double-spend protection)
    with pytest.raises(sqlite3.IntegrityError):
        db.create_payout(user1_id, "2026-06-18", 200.0, "254712345678", "PENDING", "conv3")
        
    # Verify history lists are isolated
    payouts1 = db.get_payouts(user1_id)
    payouts2 = db.get_payouts(user2_id)
    assert len(payouts1) == 1
    assert payouts1[0]["amount"] == 100.0
    assert len(payouts2) == 1
    assert payouts2[0]["amount"] == 150.0

def test_system_logs_isolation(db):
    user1_id = db.create_user("254712345678", "pass1")
    user2_id = db.create_user("254711223344", "pass2")
    
    db.log_event(user1_id, "INFO", "User 1 event")
    db.log_event(user2_id, "ERROR", "User 2 event")
    
    logs1 = db.get_logs(user1_id)
    logs2 = db.get_logs(user2_id)
    
    assert len(logs1) == 1
    assert logs1[0]["message"] == "User 1 event"
    assert logs1[0]["level"] == "INFO"
    
    assert len(logs2) == 1
    assert logs2[0]["message"] == "User 2 event"
    assert logs2[0]["level"] == "ERROR"
