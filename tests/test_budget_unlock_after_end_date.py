import pytest
import datetime
import os
import random
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id

DB_FILE = "test_budget_unlock.db"

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

def test_budget_locked_during_active_schedule_period(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(user_id, balance=1000.0)
    
    today_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    tomorrow_str = (today_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    future_str = (today_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    lock_res = client.post("/api/budget/lock", json={"start_date": tomorrow_str, "end_date": future_str})
    assert lock_res.status_code == 200
    
    # Budget is locked during schedule period
    assert db.is_budget_locked(user_id) is True
    
    # Attempting to add a budget item fails with HTTP 400
    add_res = client.post("/api/budget/items", json={"category": "Transport", "amount": 200.0})
    assert add_res.status_code == 400
    assert "locked" in add_res.json()["detail"].lower()

def test_budget_unlocked_after_end_date_passed(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(user_id, balance=1000.0)
    
    today_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    past_start = (today_dt - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    past_end = (today_dt - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    
    # Directly set past schedule dates and lock budget in database
    db.lock_budget(user_id)
    db.update_settings(user_id, start_date=past_start, end_date=past_end)
    
    # Budget is UNLOCKED because today > end_date
    assert db.is_budget_locked(user_id) is False
    
    # Settings endpoint reports is_budget_locked = False
    settings_res = client.get("/api/settings")
    assert settings_res.status_code == 200
    assert settings_res.json()["is_budget_locked"] is False
    
    # User can create new budget items again!
    add_res = client.post("/api/budget/items", json={"category": "Entertainment", "amount": 150.0})
    assert add_res.status_code == 200
    assert add_res.json()["status"] == "success"
