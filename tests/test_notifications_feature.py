import pytest
import datetime
import os
import random
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id

DB_FILE = "test_notifications.db"

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

def test_create_and_list_notifications(client_and_db):
    client, db, user_id = client_and_db
    
    # 1. Initially empty
    res0 = client.get("/api/notifications")
    assert res0.status_code == 200
    data0 = res0.json()
    assert data0["unread_count"] == 0
    assert len(data0["notifications"]) == 0
    
    # 2. Create 2 notifications
    n1_id = db.create_notification(user_id, "Welcome to Bursar", "Your account is ready.", "INFO")
    n2_id = db.create_notification(user_id, "Low Balance Warning", "Your daily budget exceeds wallet balance.", "WARNING")
    
    res1 = client.get("/api/notifications")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["unread_count"] == 2
    assert len(data1["notifications"]) == 2
    # Reverse chronological order
    assert data1["notifications"][0]["id"] == n2_id
    assert data1["notifications"][0]["title"] == "Low Balance Warning"

def test_mark_notification_as_read(client_and_db):
    client, db, user_id = client_and_db
    n1_id = db.create_notification(user_id, "System Alert", "Routine maintenance scheduled.", "INFO")
    
    res1 = client.get("/api/notifications")
    assert res1.json()["unread_count"] == 1
    
    # Mark single notification as read
    read_res = client.post(f"/api/notifications/{n1_id}/read")
    assert read_res.status_code == 200
    assert read_res.json()["status"] == "success"
    
    res2 = client.get("/api/notifications")
    assert res2.json()["unread_count"] == 0
    assert res2.json()["notifications"][0]["is_read"] is True

def test_mark_all_notifications_as_read(client_and_db):
    client, db, user_id = client_and_db
    db.create_notification(user_id, "Notice 1", "Message 1", "INFO")
    db.create_notification(user_id, "Notice 2", "Message 2", "WARNING")
    
    assert client.get("/api/notifications").json()["unread_count"] == 2
    
    # Mark all as read
    read_all_res = client.post("/api/notifications/read-all")
    assert read_all_res.status_code == 200
    assert read_all_res.json()["status"] == "success"
    
    res_after = client.get("/api/notifications")
    assert res_after.json()["unread_count"] == 0
    for notif in res_after.json()["notifications"]:
        assert notif["is_read"] is True

def test_cannot_access_other_users_notification(client_and_db):
    client, db, user_id = client_and_db
    other_user_id = db.create_user("254700999888", "TestPassword123!")
    other_n_id = db.create_notification(other_user_id, "Private Alert", "Secret information", "WARNING")
    
    # User 1 attempts to mark User 2's notification as read -> 404 Not Found
    res = client.post(f"/api/notifications/{other_n_id}/read")
    assert res.status_code == 404
