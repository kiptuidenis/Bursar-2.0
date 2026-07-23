import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db, get_current_user_id
from app.db.manager import DatabaseManager

TEST_DB_FILE = "test_idempotency.db"

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


def test_deposit_initiation_idempotency_key_returns_cached_response(test_db):
    """
    Submitting deposit initiation with an Idempotency-Key header processes the transaction on first call.
    Submitting duplicate requests with the SAME Idempotency-Key header returns the cached 200 OK response
    and does NOT create duplicate deposit rows in the database.
    """
    old_db_override = app.dependency_overrides.get(get_db)
    old_auth_override = app.dependency_overrides.get(get_current_user_id)

    app.dependency_overrides[get_db] = _db_override(test_db)
    user_id = test_db.create_user("254788111222", "pinpassword")
    test_db.update_settings(user_id=user_id, phone_number="254788111222", balance=0.0)
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        client = TestClient(app)
        headers = {"Idempotency-Key": "idemp_test_uuid_10001"}
        payload = {"amount": 500.0}

        from app.db.models import Deposit

        # 1. First POST request with Idempotency-Key -> 200 OK
        res1 = client.post("/api/deposit/initiate", json=payload, headers=headers)
        assert res1.status_code == 200
        checkout_id_1 = res1.json()["checkout_request_id"]

        # Confirm 1 deposit created in DB
        deposits_first = test_db.session.query(Deposit).filter(Deposit.user_id == user_id).all()
        assert len(deposits_first) == 1

        # 2. Duplicate POST request with SAME Idempotency-Key -> 200 OK (cached response)
        res2 = client.post("/api/deposit/initiate", json=payload, headers=headers)
        assert res2.status_code == 200
        assert res2.json()["checkout_request_id"] == checkout_id_1

        # CRITICAL FINTECH IDEMPOTENCY ASSERTION:
        # DB deposits table MUST still have EXACTLY 1 deposit record (NOT 2!)
        deposits_second = test_db.session.query(Deposit).filter(Deposit.user_id == user_id).all()
        assert len(deposits_second) == 1, f"Expected 1 deposit, found {len(deposits_second)} (Idempotency key failed!)"

        # 3. New POST request with DIFFERENT Idempotency-Key -> processes as new request
        headers_new = {"Idempotency-Key": "idemp_test_uuid_10002"}
        res3 = client.post("/api/deposit/initiate", json=payload, headers=headers_new)
        assert res3.status_code == 200
        assert res3.json()["checkout_request_id"] != checkout_id_1

        # Now DB has 2 deposits
        deposits_third = test_db.session.query(Deposit).filter(Deposit.user_id == user_id).all()
        assert len(deposits_third) == 2

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if old_auth_override is not None:
            app.dependency_overrides[get_current_user_id] = old_auth_override
        else:
            app.dependency_overrides.pop(get_current_user_id, None)
