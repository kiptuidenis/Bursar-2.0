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

def test_verify_csrf_token_helper():
    token = generate_csrf_token()
    assert verify_csrf_token(token, token) is True
    assert verify_csrf_token("invalid", token) is False
    assert verify_csrf_token(token, "invalid") is False
    assert verify_csrf_token(None, token) is False
    assert verify_csrf_token(token, None) is False

def test_csrf_missing_header_rejected():
    client = TestClient(app)
    # Signup & Login to establish valid session
    client.post("/api/auth/signup", json={"phone_number": "254711122233", "password": "Str0ng!P@ssw0rd"})
    client.post("/api/auth/login", json={"phone_number": "254711122233", "password": "Str0ng!P@ssw0rd"})

    # Attempt state-mutating profile update with session cookie but NO X-CSRF-Token header
    res_err = client.post("/api/profile", json={"first_name": "Test", "last_name": "User", "email": "test@example.com"})
    assert res_err.status_code == 403
    assert "CSRF token missing or invalid." in res_err.json()["detail"]

def test_csrf_missing_cookie_rejected():
    client = TestClient(app)
    client.post("/api/auth/signup", json={"phone_number": "254711122234", "password": "Str0ng!P@ssw0rd"})
    client.post("/api/auth/login", json={"phone_number": "254711122234", "password": "Str0ng!P@ssw0rd"})
    
    token = generate_csrf_token()
    # Delete csrf_token cookie but send header
    client.cookies.delete("csrf_token")

    res_err = client.post("/api/profile", json={"first_name": "Test"}, headers={"X-CSRF-Token": token})
    assert res_err.status_code == 403
    assert "CSRF token missing or invalid." in res_err.json()["detail"]

def test_csrf_mismatched_token_rejected():
    client = TestClient(app)
    client.post("/api/auth/signup", json={"phone_number": "254711122235", "password": "Str0ng!P@ssw0rd"})
    client.post("/api/auth/login", json={"phone_number": "254711122235", "password": "Str0ng!P@ssw0rd"})
    
    token2 = generate_csrf_token()
    # Send mismatched X-CSRF-Token header
    res_err = client.post("/api/profile", json={"first_name": "Test"}, headers={"X-CSRF-Token": token2})
    assert res_err.status_code == 403
    assert "CSRF token missing or invalid." in res_err.json()["detail"]

def test_csrf_valid_token_accepted():
    client = TestClient(app)
    # Signup & Login
    client.post("/api/auth/signup", json={"phone_number": "254711122244", "password": "Str0ng!P@ssw0rd"})
    res_login = client.post("/api/auth/login", json={"phone_number": "254711122244", "password": "Str0ng!P@ssw0rd"})
    assert res_login.status_code == 200
    
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token is not None

    # State-mutating request with matching csrf_token cookie & X-CSRF-Token header succeeds
    res_ok = client.post("/api/profile", json={"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"}, headers={"X-CSRF-Token": csrf_token})
    assert res_ok.status_code == 200

def test_csrf_safe_methods_exempt():
    client = TestClient(app)
    # GET request doesn't require CSRF header
    res_get = client.get("/api/auth/config")
    assert res_get.status_code == 200

def test_csrf_exempt_public_endpoints():
    client = TestClient(app)
    # Login & Signup public endpoints don't require CSRF header
    res_signup = client.post("/api/auth/signup", json={"phone_number": "254711122255", "password": "Str0ng!P@ssw0rd"})
    assert res_signup.status_code == 200

    res_login = client.post("/api/auth/login", json={"phone_number": "254711122255", "password": "Str0ng!P@ssw0rd"})
    assert res_login.status_code == 200

def test_csrf_token_rotation():
    client = TestClient(app)
    res_signup = client.post("/api/auth/signup", json={"phone_number": "254711122266", "password": "Str0ng!P@ssw0rd"})
    token1 = client.cookies.get("csrf_token")
    assert token1 is not None

    # Login rotates token
    res_login = client.post("/api/auth/login", json={"phone_number": "254711122266", "password": "Str0ng!P@ssw0rd"})
    token2 = client.cookies.get("csrf_token")
    assert token2 is not None
    assert token1 != token2
