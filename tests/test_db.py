import os
import pytest
import sqlite3
import sqlalchemy
from app.db.manager import DatabaseManager

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
    
    # Try duplicate registration (must raise sqlalchemy.exc.IntegrityError)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
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
    db.update_settings(user1_id, balance=3500.0, daily_budget=150.0, mode="live")
    
    # Verify settings updated for user 1, but user 2 remains unchanged
    s1 = db.get_settings(user1_id)
    s2 = db.get_settings(user2_id)
    assert s1["balance"] == 3500.0
    assert s1["daily_budget"] == 150.0
    assert s1["mode"] == "live"
    
    assert s2["balance"] == 0.0
    assert s2["daily_budget"] == 0.0
    assert s2["mode"] == "sandbox"

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
    with pytest.raises(sqlalchemy.exc.IntegrityError):
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

def test_budget_items_operations(db):
    user1_id = db.create_user("254712345678", "pass1")
    user2_id = db.create_user("254711223344", "pass2")
    
    # Verify both start with empty allocations
    items1 = db.get_budget_items(user1_id)
    items2 = db.get_budget_items(user2_id)
    assert len(items1) == 0
    assert len(items2) == 0
    
    # Add items for user 1
    id1 = db.add_or_update_budget_item(user1_id, "Food", 300.0)
    id2 = db.add_or_update_budget_item(user1_id, "Fare", 150.0)
    assert id1 is not None
    assert id2 is not None
    
    # Verify sum in daily_budget settings
    settings1 = db.get_settings(user1_id)
    assert settings1["daily_budget"] == 450.0
    
    # Verify multi-tenant isolation (user 2 still has daily_budget 0)
    settings2 = db.get_settings(user2_id)
    assert settings2["daily_budget"] == 0.0
    
    # Update category amount for user 1
    db.add_or_update_budget_item(user1_id, "Food", 350.0)
    settings1_updated = db.get_settings(user1_id)
    assert settings1_updated["daily_budget"] == 500.0
    
    # Delete item and verify recalculation
    db.delete_budget_item(user1_id, id2) # delete Fare
    settings1_deleted = db.get_settings(user1_id)
    assert settings1_deleted["daily_budget"] == 350.0

def test_budget_and_deposit_locking(db):
    user_id = db.create_user("254712345678", "pass1")
    db.adjust_balance(user_id, 2000)
    
    # Initially unlocked
    assert db.is_budget_locked(user_id) is False
    assert db.is_deposit_locked(user_id) is False
    
    # Lock budget
    db.lock_budget(user_id)
    assert db.is_budget_locked(user_id) is True
    
    # Lock deposit
    db.lock_deposit(user_id)
    assert db.is_deposit_locked(user_id) is True
    
    # Verify values stored
    settings = db.get_settings(user_id)
    assert settings["budget_locked_until"] != ""
    assert settings["deposit_locked_until"] != ""

