import os
import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.core.csrf import generate_csrf_token, verify_csrf_token
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession, OtpCode

DB_FILE = "test_csrf_protection.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

@pytest.fixture(autouse=True)
def clean_db():
    global test_db_manager
    if test_db_manager:
        test_db_manager.close()
        test_db_manager = None
    for f in (DB_FILE, DB_FILE + "-shm", DB_FILE + "-wal"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
    os.environ["TESTING_CSRF_STRICT"] = "1"
    app.dependency_overrides[get_db] = get_test_db
    yield
    os.environ.pop("TESTING_CSRF_STRICT", None)
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

def _setup_session(phone_number="254711122233"):
    client = TestClient(app)
    db = get_test_db()
    email_clean = f"user_{phone_number}@example.com"
    pwd_hash, salt = db._hash_password("Str0ng!P@ssw0rd")
    user_id = db.create_user_email(email_clean, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    client.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    client.cookies.set("csrf_token", csrf)
    return client, csrf

def test_verify_csrf_token_helper():
    token = generate_csrf_token()
    assert verify_csrf_token(token, token) is True
    assert verify_csrf_token("invalid", token) is False
    assert verify_csrf_token(token, "invalid") is False
    assert verify_csrf_token(None, token) is False
    assert verify_csrf_token(token, None) is False

def test_csrf_missing_header_rejected():
    client, csrf_token = _setup_session("254711122233")

    # Attempt state-mutating profile update with session cookie but NO X-CSRF-Token header
    res_err = client.post("/api/profile", json={"first_name": "Test", "last_name": "User", "email": "test@example.com"})
    assert res_err.status_code == 403
    assert "CSRF token missing or invalid." in res_err.json()["detail"]

def test_csrf_missing_cookie_rejected():
    client, csrf_token = _setup_session("254711122234")
    
    # Delete csrf_token cookie but send header
    client.cookies.delete("csrf_token")

    res_err = client.post("/api/profile", json={"first_name": "Test"}, headers={"X-CSRF-Token": csrf_token})
    assert res_err.status_code == 403
    assert "CSRF token missing or invalid." in res_err.json()["detail"]

def test_csrf_mismatched_token_rejected():
    client, csrf_token = _setup_session("254711122235")
    
    token2 = generate_csrf_token()
    # Send mismatched X-CSRF-Token header
    res_err = client.post("/api/profile", json={"first_name": "Test"}, headers={"X-CSRF-Token": token2})
    assert res_err.status_code == 403
    assert "CSRF token missing or invalid." in res_err.json()["detail"]

def test_csrf_valid_token_accepted():
    client, csrf_token = _setup_session("254711122244")

    # State-mutating request with matching csrf_token cookie & X-CSRF-Token header succeeds
    res_ok = client.post("/api/profile", json={"first_name": "Jane", "last_name": "Doe", "email": "user_254711122244@example.com"}, headers={"X-CSRF-Token": csrf_token})
    assert res_ok.status_code == 200

def test_csrf_safe_methods_exempt():
    client = TestClient(app)
    # GET request doesn't require CSRF header
    res_get = client.get("/api/auth/config")
    assert res_get.status_code == 200

def test_csrf_exempt_public_endpoints():
    client = TestClient(app)
    # Login & Signup public endpoints don't require CSRF header
    res_signup = client.post("/api/auth/signup", json={"email": "public_test@example.com", "password": "Str0ng!P@ssw0rd"})
    assert res_signup.status_code == 200

def test_csrf_token_rotation():
    client, token1 = _setup_session("254711122266")
    assert token1 is not None

    # Password change rotates CSRF token
    res = client.post("/api/profile/password", json={"current_password": "Str0ng!P@ssw0rd", "new_password": "NewStr0ng!P@ss2026"}, headers={"X-CSRF-Token": token1})
    assert res.status_code == 200
    csrf_cookies = [c.value for c in client.cookies.jar if c.name == "csrf_token"]
    assert len(csrf_cookies) > 0
    token2 = csrf_cookies[-1]
    assert token1 != token2
