import os
import pytest
import concurrent.futures
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db, get_current_user_id
from app.db.manager import DatabaseManager

TEST_DB_FILE = "test_concurrency.db"

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


def _db_override(db_file):
    def override():
        db = DatabaseManager(db_file)
        try:
            yield db
        finally:
            db.close()
    return override


def test_concurrent_webhook_and_polling_deposit_race_condition(test_db):
    """
    Simulates 20 simultaneous parallel requests (10 Webhook Callbacks + 10 Frontend Status Polls)
    hitting the server at the exact same millisecond for the same deposit.
    Verifies atomic DB updates prevent double-crediting so balance increases by EXACTLY 1x amount.
    """
    old_db_override = app.dependency_overrides.get(get_db)
    old_auth_override = app.dependency_overrides.get(get_current_user_id)

    app.dependency_overrides[get_db] = _db_override(TEST_DB_FILE)

    try:
        user_id = test_db.create_user("254711111222", "password")
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        test_db.update_settings(user_id=user_id, balance=0.0)

        checkout_id = "req_race_deposit_1000"
        amount = 1000.0
        test_db.create_deposit(user_id=user_id, checkout_request_id=checkout_id, amount=amount)

        # Confirm initial state
        assert test_db.get_deposit(checkout_id)["status"] == "PENDING"
        assert test_db.get_settings(user_id)["balance"] == 0.0

        client = TestClient(app)

        def fire_webhook():
            c = TestClient(app)
            return c.post(
                "/api/callbacks/intasend-webhook",
                json={"invoice_id": checkout_id, "challenge": "testnet"}
            )

        def fire_polling():
            c = TestClient(app)
            return c.get(f"/api/deposit/status/{checkout_id}")

        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            for _ in range(10):
                tasks.append(executor.submit(fire_webhook))
                tasks.append(executor.submit(fire_polling))

            results = [task.result() for task in concurrent.futures.as_completed(tasks)]

        # All requests must complete successfully (200 OK or acknowledged)
        for res in results:
            assert res.status_code == 200

        # CRITICAL FINTECH ASSERTIONS
        final_deposit = test_db.get_deposit(checkout_id)
        assert final_deposit["status"] == "SUCCESS"

        # Balance MUST be exactly 1000.0 (NOT 2000.0, NOT 20,000.0!)
        final_balance = test_db.get_settings(user_id)["balance"]
        assert final_balance == 1000.0, f"DOUBLE-CREDITING DETECTED! Expected balance 1000.0, got {final_balance}"

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if old_auth_override is not None:
            app.dependency_overrides[get_current_user_id] = old_auth_override
        else:
            app.dependency_overrides.pop(get_current_user_id, None)


def test_concurrent_payout_execution_race_condition(test_db):
    """
    Simulates 15 simultaneous parallel requests attempting to execute or confirm the same payout.
    Verifies payout is marked SUCCESS exactly once and balance is deducted exactly once.
    """
    old_db_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(TEST_DB_FILE)

    try:
        user_id = test_db.create_user("254722222333", "password")
        initial_balance = 5000.0
        payout_amount = 500.0
        test_db.update_settings(user_id=user_id, balance=initial_balance)

        conv_id = "conv_race_payout_500"
        test_db.create_payout(
            user_id=user_id,
            payout_date="2026-07-23",
            amount=payout_amount,
            phone_number="254722222333",
            status="PENDING",
            conversation_id=conv_id
        )

        client = TestClient(app)

        def fire_payout_webhook():
            c = TestClient(app)
            return c.post(
                "/api/callbacks/intasend-webhook",
                json={"tracking_id": conv_id, "challenge": "testnet"}
            )

        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            for _ in range(15):
                tasks.append(executor.submit(fire_payout_webhook))

            results = [task.result() for task in concurrent.futures.as_completed(tasks)]

        for res in results:
            assert res.status_code == 200

        # CRITICAL FINTECH ASSERTIONS
        payout = test_db.get_payouts(user_id=user_id)[0]
        assert payout["status"] == "SUCCESS"

        # Balance MUST be exactly 5000.0 - 500.0 = 4500.0 (NOT 0.0 or negative!)
        final_balance = test_db.get_settings(user_id)["balance"]
        assert final_balance == 4500.0, f"DOUBLE-DEDUCTION DETECTED! Expected balance 4500.0, got {final_balance}"

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)
