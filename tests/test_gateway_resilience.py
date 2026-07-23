import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db, get_current_user_id
from app.db.manager import DatabaseManager

TEST_DB_FILE = "test_resilience.db"

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


def test_duplicate_webhook_replay_attack_ignored(test_db):
    """
    Sends duplicate webhook callbacks for the same deposit.
    Verifies that the first callback credits the deposit, and the second replay is safely ignored without crediting balance twice.
    """
    old_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        user_id = test_db.create_user("254700111222", "password")
        test_db.update_settings(user_id=user_id, balance=100.0)

        checkout_id = "req_replay_deposit_500"
        amount = 500.0
        test_db.create_deposit(user_id=user_id, checkout_request_id=checkout_id, amount=amount)

        client = TestClient(app)
        webhook_payload = {
            "invoice_id": checkout_id,
            "challenge": "testnet"
        }

        # 1. First webhook confirmation -> 200 OK, acknowledged
        res1 = client.post("/api/callbacks/intasend-webhook", json=webhook_payload)
        assert res1.status_code == 200
        assert res1.json()["status"] == "acknowledged"
        assert test_db.get_settings(user_id)["balance"] == 600.0  # 100 + 500

        # 2. Duplicate replay attack webhook -> 200 OK, ignored!
        res2 = client.post("/api/callbacks/intasend-webhook", json=webhook_payload)
        assert res2.status_code == 200
        assert res2.json()["status"] == "ignored"

        # Balance MUST still be 600.0 (NOT 1100.0!)
        assert test_db.get_settings(user_id)["balance"] == 600.0

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)


def test_duplicate_payout_webhook_replay_attack_ignored(test_db):
    """
    Sends duplicate payout callbacks for the same tracking ID.
    Verifies that balance is deducted exactly once, and duplicate replays are ignored.
    """
    old_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        user_id = test_db.create_user("254700333444", "password")
        test_db.update_settings(user_id=user_id, balance=2000.0)

        conv_id = "conv_replay_payout_300"
        test_db.create_payout(
            user_id=user_id,
            payout_date="2026-07-23",
            amount=300.0,
            phone_number="254700333444",
            status="PENDING",
            conversation_id=conv_id
        )

        client = TestClient(app)
        payout_payload = {
            "tracking_id": conv_id,
            "challenge": "testnet"
        }

        # First payout callback -> acknowledged, balance = 1700
        res1 = client.post("/api/callbacks/intasend-webhook", json=payout_payload)
        assert res1.status_code == 200
        assert res1.json()["status"] == "acknowledged"
        assert test_db.get_settings(user_id)["balance"] == 1700.0

        # Duplicate replay -> ignored, balance remains 1700
        res2 = client.post("/api/callbacks/intasend-webhook", json=payout_payload)
        assert res2.status_code == 200
        assert res2.json()["status"] == "ignored"
        assert test_db.get_settings(user_id)["balance"] == 1700.0

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_gateway_status_error_leaves_transaction_pending(test_db, monkeypatch):
    """
    Simulates external payment gateway returning 500 error or connection failure during status double-check.
    Verifies transaction status remains PENDING and user balance is untouched.
    """
    old_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        user_id = test_db.create_user("254700555666", "password")
        test_db.update_settings(user_id=user_id, balance=500.0)

        checkout_id = "req_err_deposit_250"
        test_db.create_deposit(user_id=user_id, checkout_request_id=checkout_id, amount=250.0)

        # Mock check_stk_status to raise Gateway Exception
        async def mock_error_stk(cid, settings):
            raise RuntimeError("IntaSend API Gateway Timeout 504")

        monkeypatch.setattr("app.api.routers.callbacks.check_stk_status", mock_error_stk)

        client = TestClient(app)
        res = client.post(
            "/api/callbacks/intasend-webhook",
            json={"invoice_id": checkout_id, "challenge": "testnet"}
        )
        assert res.status_code == 200

        # Deposit status MUST remain PENDING and balance unchanged (500.0)
        assert test_db.get_deposit(checkout_id)["status"] == "PENDING"
        assert test_db.get_settings(user_id)["balance"] == 500.0

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)
