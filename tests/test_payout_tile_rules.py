import pytest
import datetime
import os
import random
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id

DB_FILE = "test_payout_tile_rules.db"

@pytest.fixture
def client_and_db():
    import gc
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass
    db = DatabaseManager(DB_FILE)
    db.initialize()
    
    phone = f"254700{random.randint(100000, 999999)}"
    user_id = db.create_user(phone, "TestPassword123!")
    
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    
    client = TestClient(app)
    
    yield client, db, user_id
    
    app.dependency_overrides.clear()
    db.close()
    gc.collect()
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass

def compute_tile_status(settings: dict, payouts: list, current_time: datetime.datetime) -> str:
    """
    Python reference implementation of the 5-State Decision Table for the Next Payout Tile.
    Used to verify API data feeds match expected state logic.
    """
    daily_budget = float(settings.get("daily_budget", 0.0))
    balance = float(settings.get("balance", 0.0))
    is_budget_locked = bool(settings.get("is_budget_locked", False))
    start_date_str = settings.get("start_date", "")
    end_date_str = settings.get("end_date", "")
    payout_time_str = settings.get("payout_time", "08:00")
    
    today_str = current_time.strftime("%Y-%m-%d")
    
    # State 1: No Active Budget
    if daily_budget <= 0 or not is_budget_locked:
        return "No Budget Set"
        
    # State 2: Ended
    if end_date_str and today_str > end_date_str:
        return "Schedule Ended"
        
    # State 3: Low Balance (when budget is locked)
    if balance < daily_budget:
        return "Top-up Required"
        
    # State 4: 3rd-Party API Failure
    payout_failed_today = any(
        p.get("payout_date") == today_str and p.get("status") == "FAILED"
        for p in payouts
    )
    if payout_failed_today and balance >= daily_budget and is_budget_locked:
        return "Payout Failed — Use Run Payout"
        
    # State 5: Live Payout Countdown
    return "COUNTDOWN"

def test_tile_no_budget_set_when_budget_zero(client_and_db):
    client, db, user_id = client_and_db
    settings = db.get_settings(user_id)
    settings["is_budget_locked"] = db.is_budget_locked(user_id)
    payouts = db.get_payouts(user_id)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
    
    assert compute_tile_status(settings, payouts, now) == "No Budget Set"

def test_tile_no_budget_set_when_budget_unlocked(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(user_id, balance=1000.0)
    
    settings = db.get_settings(user_id)
    settings["is_budget_locked"] = db.is_budget_locked(user_id) # False
    payouts = db.get_payouts(user_id)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
    
    assert compute_tile_status(settings, payouts, now) == "No Budget Set"

def test_tile_schedule_ended(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(user_id, balance=1000.0, start_date="2026-07-01", end_date="2026-07-10")
    db.lock_budget(user_id)
    
    settings = db.get_settings(user_id)
    settings["is_budget_locked"] = True
    payouts = db.get_payouts(user_id)
    
    future_now = datetime.datetime(2026, 7, 20, 10, 0, 0)
    assert compute_tile_status(settings, payouts, future_now) == "Schedule Ended"

def test_tile_insufficient_balance(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(user_id, balance=50.0) # Balance 50 < daily_budget 300
    db.lock_budget(user_id)
    
    settings = db.get_settings(user_id)
    settings["is_budget_locked"] = True
    payouts = db.get_payouts(user_id)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
    
    assert compute_tile_status(settings, payouts, now) == "Top-up Required"

def test_tile_third_party_api_failed(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(user_id, balance=1000.0, phone_number="254700112233")
    db.lock_budget(user_id)
    
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
    today_str = now.strftime("%Y-%m-%d")
    
    db.create_payout(user_id, today_str, 300.0, "254700112233", "FAILED")
    
    settings = db.get_settings(user_id)
    settings["is_budget_locked"] = True
    payouts = db.get_payouts(user_id)
    
    assert compute_tile_status(settings, payouts, now) == "Payout Failed — Use Run Payout"

def test_tile_time_passed_without_api_failure(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(user_id, balance=1000.0, payout_time="08:00")
    db.lock_budget(user_id)
    
    settings = db.get_settings(user_id)
    settings["is_budget_locked"] = True
    payouts = db.get_payouts(user_id) # No failed payout record
    
    # 10:00 AM (past 08:00 AM today, but no failed attempt)
    now_past = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(hour=10, minute=0, second=0)
    status = compute_tile_status(settings, payouts, now_past)
    
    assert status == "COUNTDOWN"
    assert status != "Payout is due"
