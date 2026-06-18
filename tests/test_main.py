import pytest
import os
import json
from fastapi.testclient import TestClient
from app.db import DatabaseManager
from app.main import app, get_db

DB_FILE = "test_api_multitenant.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

app.dependency_overrides[get_db] = get_test_db

@pytest.fixture(autouse=True)
def clean_db():
    db = get_test_db()
    conn = db.connection
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM settings")
    cursor.execute("DELETE FROM payouts")
    cursor.execute("DELETE FROM logs")
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    yield

client = TestClient(app)

def test_unauthenticated_requests():
    # Calling settings, deposits, payouts, etc. without auth must return 401
    r1 = client.get("/api/settings")
    assert r1.status_code == 401
    assert "required" in r1.json()["detail"].lower()
    
    r2 = client.post("/api/deposit", json={"amount": 100})
    assert r2.status_code == 401
    
    r3 = client.get("/api/payouts")
    assert r3.status_code == 401

def test_signup_and_login_flow():
    # 1. Sign up new user
    signup_payload = {
        "phone_number": "254712345678",
        "password": "mypassword123"
    }
    res_signup = client.post("/api/auth/signup", json=signup_payload)
    assert res_signup.status_code == 200
    assert res_signup.json()["status"] == "success"
    
    # Sign up duplicate must fail
    res_dup = client.post("/api/auth/signup", json=signup_payload)
    assert res_dup.status_code == 400
    
    # 2. Login
    login_payload = {
        "phone_number": "254712345678",
        "password": "mypassword123"
    }
    
    # We use a fresh client to isolate cookie state
    c = TestClient(app)
    res_login = c.post("/api/auth/login", json=login_payload)
    assert res_login.status_code == 200
    assert "session_token" in res_login.cookies
    
    # 3. Verify /me endpoint
    res_me = c.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["phone_number"] == "254712345678"
    
    # 4. Access protected settings (should succeed now)
    res_settings = c.get("/api/settings")
    assert res_settings.status_code == 200
    assert res_settings.json()["balance"] == 0.0
    
    # 5. Logout
    res_logout = c.post("/api/auth/logout")
    assert res_logout.status_code == 200
    
    # Post logout, settings access should fail again
    res_settings_post = c.get("/api/settings")
    assert res_settings_post.status_code == 401

def test_user_data_isolation_via_api():
    # Create User A and User B
    client_a = TestClient(app)
    client_a.post("/api/auth/signup", json={"phone_number": "254711111111", "password": "pass"})
    client_a.post("/api/auth/login", json={"phone_number": "254711111111", "password": "pass"})
    
    client_b = TestClient(app)
    client_b.post("/api/auth/signup", json={"phone_number": "254722222222", "password": "pass"})
    client_b.post("/api/auth/login", json={"phone_number": "254722222222", "password": "pass"})
    
    # User A deposits 1000
    res_dep_a = client_a.post("/api/deposit", json={"amount": 1000.0})
    assert res_dep_a.json()["new_balance"] == 1000.0
    
    # User B deposits 500
    res_dep_b = client_b.post("/api/deposit", json={"amount": 500.0})
    assert res_dep_b.json()["new_balance"] == 500.0
    
    # Verify User A still has 1000, and User B has 500
    assert client_a.get("/api/settings").json()["balance"] == 1000.0
    assert client_b.get("/api/settings").json()["balance"] == 500.0

def test_settings_masked_updates_multi_tenant():
    c = TestClient(app)
    res_signup = c.post("/api/auth/signup", json={"phone_number": "254712345678", "password": "pass"})
    user_id = res_signup.json()["user_id"]
    c.post("/api/auth/login", json={"phone_number": "254712345678", "password": "pass"})
    
    payload = {
        "balance": 200.0,
        "daily_budget": 50.0,
        "mpesa_consumer_secret": "secret_key"
    }
    c.post("/api/settings", json=payload)
    
    # Check mask
    res1 = c.get("/api/settings").json()
    assert res1["mpesa_consumer_secret"] == "********"
    
    # Update balance with mask submitted (should preserve secret)
    c.post("/api/settings", json={"balance": 500.0, "mpesa_consumer_secret": "********"})
    
    db = get_test_db()
    settings = db.get_settings(user_id=user_id)
    assert settings["balance"] == 500.0
    assert settings["mpesa_consumer_secret"] == "secret_key"

def test_b2c_callbacks_success_and_failure():
    # 1. Signup user
    c = TestClient(app)
    res_signup = c.post("/api/auth/signup", json={"phone_number": "254712345678", "password": "pass"})
    user_id = res_signup.json()["user_id"]
    c.post("/api/auth/login", json={"phone_number": "254712345678", "password": "pass"})
    
    # 2. Add pending payout in database manually for User
    db = get_test_db()
    db.create_payout(
        user_id=user_id,
        payout_date="2026-06-18",
        amount=300.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id="conv_abc"
    )
    db.update_settings(user_id=user_id, balance=700.0) # Pre-deducted
    
    # 3. Trigger callback for success (anonymous webhook)
    success_payload = {
        "Result": {
            "ResultType": 0,
            "ResultCode": 0,
            "ResultDesc": "Success",
            "ConversationID": "conv_abc",
            "TransactionID": "MPESA123",
            "ResultParameters": None
        }
    }
    # Callback route does not require authentication
    res_cb = client.post("/api/callbacks/b2c-result", json=success_payload)
    assert res_cb.status_code == 200
    assert res_cb.json()["status"] == "acknowledged"
    
    # Verify DB state
    payout = db.get_payouts(user_id=user_id)[0]
    assert payout["status"] == "SUCCESS"
    assert payout["transaction_id"] == "MPESA123"
    assert db.get_settings(user_id=user_id)["balance"] == 700.0
    
    # 4. Add failed payout for User
    db.create_payout(
        user_id=user_id,
        payout_date="2026-06-19",
        amount=250.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id="conv_fail"
    )
    db.update_settings(user_id=user_id, balance=450.0) # Pre-deducted
    
    # Trigger callback for failure (anonymous webhook)
    fail_payload = {
        "Result": {
            "ResultType": 0,
            "ResultCode": 1032, # Cancelled
            "ResultDesc": "Request cancelled.",
            "ConversationID": "conv_fail",
            "TransactionID": "",
            "ResultParameters": None
        }
    }
    res_cb_fail = client.post("/api/callbacks/b2c-result", json=fail_payload)
    assert res_cb_fail.status_code == 200
    
    # Verify DB state (should be FAILED and balance refunded)
    payout_fail = db.get_payouts(user_id=user_id)[0]
    assert payout_fail["status"] == "FAILED"
    assert db.get_settings(user_id=user_id)["balance"] == 700.0  # 450 + 250 refund
