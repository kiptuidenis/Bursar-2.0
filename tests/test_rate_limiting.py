import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db, get_current_user_id
from app.core import config
from app.db.manager import DatabaseManager

TEST_DB_FILE = "test_rate_limit.db"

@pytest.fixture
def test_db():
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass

    manager = DatabaseManager(TEST_DB_FILE)
    manager.initialize()
    yield manager
    manager.close()

    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


def _db_override(manager):
    def override():
        yield manager
    return override


def test_login_rate_limiting_triggers_429_on_6th_attempt(test_db, monkeypatch):
    """
    Firing 5 consecutive login POSTs succeeds/fails normally.
    The 6th consecutive login POST from the same IP must trigger 429 Too Many Requests with Retry-After header.
    """
    # Force rate limiting enabled for this specific test
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", True)

    old_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        user_id = test_db.create_user("254799000111", "pinpassword")
        client = TestClient(app)

        login_payload = {"phone_number": "254799000111", "password": "wrongpassword"}

        # First 4 attempts -> 401 Unauthorized (normal authentication error)
        for i in range(4):
            res = client.post("/api/auth/login", json=login_payload)
            assert res.status_code == 401, f"Attempt {i+1} failed expected 401, got {res.status_code}"

        # 5th attempt -> 429 Too Many Requests / Account Lockout!
        res_limit = client.post("/api/auth/login", json=login_payload)
        assert res_limit.status_code == 429, f"5th attempt expected 429, got {res_limit.status_code}"
        assert "retry-after" in [h.lower() for h in res_limit.headers.keys()]

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)


def test_deposit_initiation_rate_limiting_triggers_429(test_db, monkeypatch):
    """
    Firing 5 rapid deposit initiation requests succeeds.
    The 6th request triggers 429 Too Many Requests.
    """
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", True)

    old_db_override = app.dependency_overrides.get(get_db)
    old_auth_override = app.dependency_overrides.get(get_current_user_id)

    app.dependency_overrides[get_db] = _db_override(test_db)
    user_id = test_db.create_user("254799000222", "pinpassword")
    test_db.update_settings(user_id=user_id, phone_number="254799000222", balance=0.0)
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        client = TestClient(app)
        deposit_payload = {"amount": 500.0}

        for i in range(5):
            res = client.post("/api/deposit/initiate", json=deposit_payload)
            assert res.status_code == 200, f"Attempt {i+1} expected 200, got {res.status_code}"

        # 6th attempt -> 429 Too Many Requests
        res_limit = client.post("/api/deposit/initiate", json=deposit_payload)
        assert res_limit.status_code == 429, f"6th attempt expected 429, got {res_limit.status_code}"

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if old_auth_override is not None:
            app.dependency_overrides[get_current_user_id] = old_auth_override
        else:
            app.dependency_overrides.pop(get_current_user_id, None)


def test_password_change_rate_limiting_triggers_429(test_db, monkeypatch):
    """Firing 5 rapid password change requests succeeds/fails normally; 6th attempt triggers 429."""
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", True)

    old_db_override = app.dependency_overrides.get(get_db)
    old_auth_override = app.dependency_overrides.get(get_current_user_id)

    app.dependency_overrides[get_db] = _db_override(test_db)
    user_id = test_db.create_user("254799000333", "pinpassword")
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        client = TestClient(app)
        pw_payload = {"current_password": "pinpassword", "new_password": "newpassword123"}

        for i in range(5):
            res = client.post("/api/profile/password", json=pw_payload)
            # 1st succeeds (200), subsequent fails wrong current password (401), but all execute normally
            assert res.status_code in (200, 401), f"Attempt {i+1} got {res.status_code}"

        # 6th attempt -> 429 Too Many Requests
        res_limit = client.post("/api/profile/password", json=pw_payload)
        assert res_limit.status_code == 429, f"6th attempt expected 429, got {res_limit.status_code}"

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if old_auth_override is not None:
            app.dependency_overrides[get_current_user_id] = old_auth_override
        else:
            app.dependency_overrides.pop(get_current_user_id, None)


def test_payout_trigger_rate_limiting_triggers_429(test_db, monkeypatch):
    """Firing 5 rapid manual payout trigger requests succeeds/fails normally; 6th attempt triggers 429."""
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", True)

    old_db_override = app.dependency_overrides.get(get_db)
    old_auth_override = app.dependency_overrides.get(get_current_user_id)

    app.dependency_overrides[get_db] = _db_override(test_db)
    user_id = test_db.create_user("254799000444", "pinpassword")
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        client = TestClient(app)

        for i in range(5):
            res = client.post("/api/payout/trigger")
            assert res.status_code == 200, f"Attempt {i+1} expected 200, got {res.status_code}"

        # 6th attempt -> 429 Too Many Requests
        res_limit = client.post("/api/payout/trigger")
        assert res_limit.status_code == 429, f"6th attempt expected 429, got {res_limit.status_code}"

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if old_auth_override is not None:
            app.dependency_overrides[get_current_user_id] = old_auth_override
        else:
            app.dependency_overrides.pop(get_current_user_id, None)
