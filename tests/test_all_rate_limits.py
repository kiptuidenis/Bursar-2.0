import os
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.core import config

DB_FILE = "test_all_rate_limits.db"
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


@pytest.fixture
def enable_limiter(monkeypatch):
    """Fixture to enable slowapi rate limiter explicitly for rate limit tests."""
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", True)
        try:
            app.state.limiter.reset()
        except Exception:
            pass
    yield
    monkeypatch.setattr(config, "IS_TEST_MODE", True)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", False)
        try:
            app.state.limiter.reset()
        except Exception:
            pass


from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

def _setup_auth_client(phone_number, password="Str0ng!P@ssw0rdRL"):
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

def test_profile_rate_limits_trigger_429(enable_limiter):
    """Verify rate limits on /api/profile/password and /api/profile/deactivate."""
    client, headers = _setup_auth_client("254711666000")

    # 1. Change password limit (5/minute) -> 6th attempt returns 429
    for i in range(5):
        client.post("/api/profile/password", json={"current_password": "WrongPassword!", "new_password": "Str0ng!P@ssw0rdRL2"}, headers=headers)

    res_cp = client.post("/api/profile/password", json={"current_password": "WrongPassword!", "new_password": "Str0ng!P@ssw0rdRL2"}, headers=headers)
    assert res_cp.status_code == 429

    # 2. Deactivate limit (3/minute) -> 4th attempt returns 429
    for i in range(3):
        client.post("/api/profile/deactivate", json={"password": "WrongPassword!", "confirmation": "DELETE", "otp_code": "123456"}, headers=headers)

    res_deact = client.post("/api/profile/deactivate", json={"password": "WrongPassword!", "confirmation": "DELETE", "otp_code": "123456"}, headers=headers)
    assert res_deact.status_code == 429


def test_notifications_rate_limits_trigger_429(enable_limiter):
    """Verify rate limits on /api/notifications endpoints."""
    client, headers = _setup_auth_client("254711666111")

    # read-all limit (30/minute) -> 31st attempt returns 429
    for i in range(30):
        client.post("/api/notifications/read-all", headers=headers)

    res_read_all = client.post("/api/notifications/read-all", headers=headers)
    assert res_read_all.status_code == 429


def test_payouts_rate_limits_trigger_429(enable_limiter):
    """Verify rate limit on /api/payout/trigger (5/minute)."""
    client, headers = _setup_auth_client("254711666222")

    for i in range(5):
        client.post("/api/payout/trigger", headers=headers)

    res_trigger = client.post("/api/payout/trigger", headers=headers)
    assert res_trigger.status_code == 429
