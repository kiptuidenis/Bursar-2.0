import os
import hmac
import hashlib
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.core import config

DB_FILE = "test_e2e_phase1_security.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager


@pytest.fixture(autouse=True)
def clean_db():
    for f in (DB_FILE, DB_FILE + "-shm", DB_FILE + "-wal"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    global test_db_manager
    test_db_manager = DatabaseManager(DB_FILE)
    test_db_manager.initialize()

    app.dependency_overrides[get_db] = get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)
    if test_db_manager:
        test_db_manager.close()
        test_db_manager = None
    for f in (DB_FILE, DB_FILE + "-shm", DB_FILE + "-wal"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

def test_e2e_user_journey_and_security_boundary(monkeypatch):
    """
    End-to-End User Journey Test for Phase 1 Security Fixes:
    1. User signup, login, session validation & dashboard page access.
    2. Settings interaction: Updating sensitive credentials, verifying masking of mpesa_consumer_key/secret.
    3. Balance Injection Attack Attempt: Submitting balance modification via POST /api/settings and verifying balance is unchanged.
    4. IntaSend Webhook Flow: Unauthenticated callback rejected with 401, signed SHA256 HMAC callback accepted.
    """
    monkeypatch.setattr(config, "INTASEND_WEBHOOK_CHALLENGE", "e2e_secret_challenge_key_456")
    client = TestClient(app)
    db = get_test_db()
    email_clean = "e2e_user@example.com"
    phone_number = "254711888999"
    pwd_hash, salt = db._hash_password("Str0ng!P@ssw0rdE2E")
    user_id = db.create_user_email(email_clean, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    client.cookies.set("session_token", token)
    csrf_token = generate_csrf_token()
    client.cookies.set("csrf_token", csrf_token)

    # 3. Access HTML Dashboard
    dash_res = client.get("/dashboard")
    assert dash_res.status_code == 200
    assert "text/html" in dash_res.headers["content-type"]

    # 4. Settings Update with sensitive keys
    settings_payload = {
        "mpesa_consumer_key": "my_live_consumer_key_123",
        "mpesa_consumer_secret": "my_live_consumer_secret_456",
        "mpesa_initiator_password": "my_initiator_password_789",
        "balance": 999999.0  # Malicious attempt to inject balance
    }
    update_res = client.post("/api/settings", json=settings_payload, headers={"X-CSRF-Token": csrf_token})
    assert update_res.status_code == 200

    # Add budget item via Budget domain endpoint
    client.post("/api/budget/items", json={"category": "Living", "amount": 300}, headers={"X-CSRF-Token": csrf_token})

    # 5. Fetch Settings & Verify Masking + Balance Protection
    settings_res = client.get("/api/settings")
    assert settings_res.status_code == 200
    data = settings_res.json()

    # Consumer key, secret, and password must be masked as '********'
    assert data["mpesa_consumer_key"] == "********"
    assert data["mpesa_consumer_secret"] == "********"
    assert data["mpesa_initiator_password"] == "********"

    # Balance MUST remain 0.0 (not injected to 999999.0)
    assert data["balance"] == 0.0
    assert data["daily_budget"] == 300.0

    # 6. IntaSend Webhook Callback E2E Flow
    # Initiate deposit
    client.post("/api/settings", json={"phone_number": "254711888999"}, headers={"X-CSRF-Token": csrf_token})
    dep_res = client.post("/api/deposit/initiate", json={"amount": 1500.0}, headers={"X-CSRF-Token": csrf_token})
    assert dep_res.status_code == 200
    checkout_id = dep_res.json()["checkout_request_id"]

    webhook_payload = {
        "invoice_id": checkout_id,
        "state": "COMPLETE",
        "provider": "M-PESA",
        "charges": "0.00",
        "net_amount": "1500.00",
        "currency": "KES",
        "value": "1500.00",
        "api_ref": checkout_id
    }

    # Attempt 1: Webhook without X-IntaSend-Signature header -> Blocked with 401
    bad_res1 = client.post("/api/callbacks/intasend-webhook", json=webhook_payload)
    assert bad_res1.status_code == 401

    # Attempt 2: Webhook with fake signature -> Blocked with 401
    bad_res2 = client.post("/api/callbacks/intasend-webhook", json=webhook_payload, headers={"X-IntaSend-Signature": "fake_sig_123"})
    assert bad_res2.status_code == 401

    # Attempt 3: Webhook with valid SHA-256 HMAC signature -> Accepted with 200
    body_bytes = json.dumps(webhook_payload, separators=(',', ':')).encode("utf-8")
    valid_signature = hmac.new(
        b"e2e_secret_challenge_key_456",
        body_bytes,
        hashlib.sha256
    ).hexdigest()

    good_res = client.post("/api/callbacks/intasend-webhook", json=webhook_payload, headers={"X-IntaSend-Signature": valid_signature})
    assert good_res.status_code == 200
    assert good_res.json()["status"] == "acknowledged"

    # Verify balance was updated via genuine webhook callback to 1500.0
    final_settings = client.get("/api/settings").json()
    assert final_settings["balance"] == 1500.0
