import os
import hmac
import hashlib
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.core import config
from app.core.csrf import generate_csrf_token

DB_FILE = "test_security_audit_fixes.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager


@pytest.fixture(autouse=True)
def clean_db():
    # Delete stale DB file if present to guarantee clean schema
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

def _setup_auth_client(phone_number, password="Str0ng!P@ssw0rd1"):
    client = TestClient(app)
    db = get_test_db()
    email_clean = f"user_{phone_number}@example.com"
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email_clean, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    client.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    client.cookies.set("csrf_token", csrf)
    headers = {"X-CSRF-Token": csrf}
    return client, headers

def test_balance_injection_prevented():
    """Verify that clients cannot inject or modify the wallet balance via POST /api/settings."""
    client, headers = _setup_auth_client("254711999111")

    # Verify initial settings balance is 0.0
    res_get = client.get("/api/settings")
    assert res_get.status_code == 200
    assert res_get.json()["balance"] == 0.0

    # Attempt to inject balance = 100000.0 via POST /api/settings
    res_update = client.post(
        "/api/settings",
        json={"balance": 100000.0, "daily_budget": 500.0},
        headers=headers
    )
    assert res_update.status_code == 200

    # Confirm balance remains 0.0 and was NOT updated to 100000.0
    res_get_after = client.get("/api/settings")
    assert res_get_after.status_code == 200
    assert res_get_after.json()["balance"] == 0.0
    assert res_get_after.json()["daily_budget"] == 500.0


def test_webhook_signature_verification_fail_closed(monkeypatch):
    """Verify that webhook verification fails closed when signature is missing or invalid."""
    client = TestClient(app)
    monkeypatch.setattr(config, "INTASEND_WEBHOOK_CHALLENGE", "test_webhook_secret_key_123")

    payload = {"invoice_id": "TEST_INV_001", "state": "COMPLETE", "value": "500"}

    # 1. Missing signature header -> 401
    res1 = client.post("/api/callbacks/intasend-webhook", json=payload)
    assert res1.status_code == 401
    assert "Missing signature header" in res1.json()["detail"]

    # 2. Invalid signature header -> 401
    res2 = client.post("/api/callbacks/intasend-webhook", json=payload, headers={"X-IntaSend-Signature": "invalid_sig"})
    assert res2.status_code == 401
    assert "Signature verification failed" in res2.json()["detail"]

    # 3. Valid SHA256 HMAC signature header -> Passes auth check (returns 404 for non-existent deposit or 200)
    body_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
    valid_sig = hmac.new(
        b"test_webhook_secret_key_123",
        body_bytes,
        hashlib.sha256
    ).hexdigest()

    res3 = client.post("/api/callbacks/intasend-webhook", json=payload, headers={"X-IntaSend-Signature": valid_sig})
    # Should not fail signature check (401), but may return 404 for unknown checkout_request_id
    assert res3.status_code != 401


def test_mpesa_consumer_key_masked_in_settings():
    """Verify that mpesa_consumer_key is masked alongside secret/password in settings response."""
    client, headers = _setup_auth_client("254711999222")

    # Update sensitive settings
    client.post(
        "/api/settings",
        json={"mpesa_consumer_key": "my_consumer_key_xyz", "mpesa_consumer_secret": "my_secret_123"},
        headers=headers
    )

    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["mpesa_consumer_key"] == "********"
    assert data["mpesa_consumer_secret"] == "********"
