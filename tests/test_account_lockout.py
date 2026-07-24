import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db
from app.db.manager import DatabaseManager

TEST_DB_FILE = "test_lockout.db"

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


def test_account_lockout_after_5_failed_attempts(test_db):
    """
    Submitting 4 incorrect PIN attempts returns 401 Unauthorized.
    Submitting 5th incorrect PIN attempt locks the account for 15 minutes and returns 429 Account Locked.
    Submitting a 6th attempt with the CORRECT PIN while locked is rejected with 429 Account Locked.
    """
    old_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        phone = "254755111222"
        correct_pin = "Str0ng!P@ssw0rd"
        user_id = test_db.create_user(phone, correct_pin)

        client = TestClient(app)
        wrong_payload = {"phone_number": phone, "password": "WrongP@ssw0rd!"}
        correct_payload = {"phone_number": phone, "password": correct_pin}

        # 1. Attempts 1 through 4 -> 401 Unauthorized
        for i in range(4):
            res = client.post("/api/auth/login", json=wrong_payload)
            assert res.status_code == 401, f"Attempt {i+1} expected 401, got {res.status_code}"

        # 2. 5th attempt -> 429 Account Locked!
        res_lock = client.post("/api/auth/login", json=wrong_payload)
        assert res_lock.status_code == 429, f"5th attempt expected 429, got {res_lock.status_code}"
        assert "account locked" in res_lock.json()["detail"].lower()
        assert res_lock.headers.get("retry-after") == "900"

        # 3. 6th attempt with CORRECT PIN while locked -> 429 Account Locked (PREVENTED!)
        res_correct_while_locked = client.post("/api/auth/login", json=correct_payload)
        assert res_correct_while_locked.status_code == 429
        assert "account locked" in res_correct_while_locked.json()["detail"].lower()

        # 4. Verify audit log recorded warning event
        logs = test_db.get_logs(user_id=user_id)
        lockout_log = [l for l in logs if "locked for 15 minutes" in l["message"]]
        assert len(lockout_log) > 0, "Audit log event for account lockout was not recorded."

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)
