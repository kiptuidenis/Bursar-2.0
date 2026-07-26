import pytest
import datetime
import os
import random
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id

DB_FILE = "test_schedule_dates.db"

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

def test_settings_start_date_in_past_rejected(client_and_db):
    client, db, user_id = client_and_db
    past_date = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    response = client.post("/api/settings", json={"start_date": past_date})
    assert response.status_code == 400
    assert "in the past" in response.json()["detail"].lower()

def test_settings_end_date_equal_to_start_date_rejected(client_and_db):
    client, db, user_id = client_and_db
    today_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d")
    
    response = client.post("/api/settings", json={"start_date": today_date, "end_date": today_date})
    assert response.status_code == 400
    assert "after start date" in response.json()["detail"].lower() or "same" in response.json()["detail"].lower()

def test_settings_end_date_before_start_date_rejected(client_and_db):
    client, db, user_id = client_and_db
    today_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    start_date = (today_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = (today_dt + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    
    response = client.post("/api/settings", json={"start_date": start_date, "end_date": end_date})
    assert response.status_code == 400
    assert "after start date" in response.json()["detail"].lower() or "earlier" in response.json()["detail"].lower()

def test_budget_lock_start_date_in_past_rejected(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 200.0)
    
    past_date = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    future_date = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))) + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    response = client.post("/api/budget/lock", json={"start_date": past_date, "end_date": future_date})
    assert response.status_code == 400
    assert "in the past" in response.json()["detail"].lower()

def test_budget_lock_end_date_equal_to_start_date_rejected(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 200.0)
    
    today_date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d")
    
    response = client.post("/api/budget/lock", json={"start_date": today_date, "end_date": today_date})
    assert response.status_code == 400
    assert "after start date" in response.json()["detail"].lower() or "same" in response.json()["detail"].lower()

def test_valid_schedule_dates_accepted(client_and_db):
    client, db, user_id = client_and_db
    db.add_or_update_budget_item(user_id, "Food", 200.0)
    
    today_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    start_date = today_dt.strftime("%Y-%m-%d")
    end_date = (today_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    response = client.post("/api/settings", json={"start_date": start_date, "end_date": end_date})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    lock_response = client.post("/api/budget/lock", json={"start_date": start_date, "end_date": end_date})
    assert lock_response.status_code == 200
    assert lock_response.json()["status"] == "success"
