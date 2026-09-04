import pytest
import datetime
import os
import gc
from unittest.mock import AsyncMock, patch
from app.db.manager import DatabaseManager
from app.services.scheduler import poll_pending_deposits, poll_pending_payouts

DB_FILE = "test_scheduler_polling.db"

@pytest.fixture
def db():
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass
    manager = DatabaseManager(DB_FILE)
    manager.initialize()
    yield manager
    manager.close()
    gc.collect()
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass


# ---------------------------------------------------------------------------
# poll_pending_deposits tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_pending_deposits_resolves_success(db):
    """A PENDING deposit older than 30s should be marked SUCCESS when gateway confirms."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=0.0, mode="sandbox")

    # Insert a PENDING deposit with a fake old created_at timestamp
    checkout_id = "inv_test_success_001"
    db.create_deposit(user_id, checkout_id, 500.0)
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE deposits SET created_at = ? WHERE checkout_request_id = ?", (old_ts, checkout_id))
    conn.commit()

    # Mock gateway returning SUCCESS
    mock_stk = AsyncMock(return_value={"status": "SUCCESS", "invoice_id": checkout_id, "amount": 500.0})
    with patch("app.services.scheduler.check_stk_status", mock_stk):
        await poll_pending_deposits(db)

    # Verify deposit was resolved
    deposit = db.get_deposit(checkout_id)
    assert deposit["status"] == "SUCCESS"
    assert deposit["mpesa_receipt"] == "POLL_VERIFIED"

    # Verify balance was credited
    settings = db.get_settings(user_id)
    assert settings["balance"] == 500.0

    # Verify log entry was created
    logs = db.get_logs(user_id)
    assert any("[Scheduler Poll]" in l["message"] and "SUCCESS" in l["message"] for l in logs)


@pytest.mark.asyncio
async def test_poll_pending_deposits_resolves_failed(db):
    """A PENDING deposit older than 30s should be marked FAILED when gateway confirms failure."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=0.0, mode="sandbox")

    checkout_id = "inv_test_fail_001"
    db.create_deposit(user_id, checkout_id, 200.0)
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE deposits SET created_at = ? WHERE checkout_request_id = ?", (old_ts, checkout_id))
    conn.commit()

    mock_stk = AsyncMock(return_value={"status": "FAILED", "invoice_id": checkout_id})
    with patch("app.services.scheduler.check_stk_status", mock_stk):
        await poll_pending_deposits(db)

    deposit = db.get_deposit(checkout_id)
    assert deposit["status"] == "FAILED"

    # Balance should NOT have changed
    settings = db.get_settings(user_id)
    assert settings["balance"] == 0.0


@pytest.mark.asyncio
async def test_poll_pending_deposits_ignores_recent(db):
    """A PENDING deposit younger than 30s should NOT be polled."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=0.0, mode="sandbox")

    checkout_id = "inv_test_recent_001"
    db.create_deposit(user_id, checkout_id, 300.0)
    # Do NOT backdate created_at — it was just created

    mock_stk = AsyncMock(return_value={"status": "SUCCESS"})
    with patch("app.services.scheduler.check_stk_status", mock_stk):
        await poll_pending_deposits(db)

    # Gateway should NOT have been called
    mock_stk.assert_not_called()

    # Deposit should remain PENDING
    deposit = db.get_deposit(checkout_id)
    assert deposit["status"] == "PENDING"


@pytest.mark.asyncio
async def test_poll_pending_deposits_ignores_already_resolved(db):
    """A deposit already marked SUCCESS should not be re-processed."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=500.0, mode="sandbox")

    checkout_id = "inv_test_already_done"
    db.create_deposit(user_id, checkout_id, 500.0)
    db.update_deposit_status(checkout_id, "SUCCESS", "ALREADY_DONE")

    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE deposits SET created_at = ? WHERE checkout_request_id = ?", (old_ts, checkout_id))
    conn.commit()

    mock_stk = AsyncMock(return_value={"status": "SUCCESS"})
    with patch("app.services.scheduler.check_stk_status", mock_stk):
        await poll_pending_deposits(db)

    # Should not have been called because the SQL query filters status = 'PENDING'
    mock_stk.assert_not_called()

    # Balance should remain unchanged
    assert db.get_settings(user_id)["balance"] == 500.0


@pytest.mark.asyncio
async def test_poll_pending_deposits_gateway_error_leaves_pending(db):
    """If the gateway call throws an exception, the deposit stays PENDING."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=0.0, mode="sandbox")

    checkout_id = "inv_test_error_001"
    db.create_deposit(user_id, checkout_id, 100.0)
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE deposits SET created_at = ? WHERE checkout_request_id = ?", (old_ts, checkout_id))
    conn.commit()

    mock_stk = AsyncMock(side_effect=Exception("Network timeout"))
    with patch("app.services.scheduler.check_stk_status", mock_stk):
        await poll_pending_deposits(db)

    deposit = db.get_deposit(checkout_id)
    assert deposit["status"] == "PENDING"
    assert db.get_settings(user_id)["balance"] == 0.0


@pytest.mark.asyncio
async def test_poll_pending_deposits_locks_budget(db):
    """When a deposit is confirmed SUCCESS, budget should auto-lock if items exist."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=0.0, mode="sandbox")
    db.add_or_update_budget_item(user_id, "Food", 200.0)

    checkout_id = "inv_test_lock_001"
    db.create_deposit(user_id, checkout_id, 1000.0)
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE deposits SET created_at = ? WHERE checkout_request_id = ?", (old_ts, checkout_id))
    conn.commit()

    mock_stk = AsyncMock(return_value={"status": "SUCCESS", "invoice_id": checkout_id, "amount": 1000.0})
    with patch("app.services.scheduler.check_stk_status", mock_stk):
        await poll_pending_deposits(db)

    # Budget should be locked
    assert db.is_budget_locked(user_id) is True
    # Deposit should be locked
    assert db.is_deposit_locked(user_id) is True


# ---------------------------------------------------------------------------
# poll_pending_payouts tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_pending_payouts_resolves_success(db):
    """A PENDING payout with a tracking ID older than 30s should resolve to SUCCESS."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, mode="sandbox")

    tracking_id = "track_success_001"
    payout_id = db.create_payout(
        user_id=user_id,
        payout_date="2026-06-25",
        amount=100.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id=tracking_id,
        originator_conversation_id=tracking_id
    )
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE payouts SET created_at = ? WHERE id = ?", (old_ts, payout_id))
    conn.commit()

    mock_payout_status = AsyncMock(return_value={"status": "SUCCESS", "tracking_id": tracking_id})
    with patch("app.services.scheduler.check_payout_status", mock_payout_status):
        await poll_pending_payouts(db)

    payout = db.get_payout_by_conversation_id(tracking_id)
    assert payout["status"] == "SUCCESS"

    # Balance should have been deducted
    settings = db.get_settings(user_id)
    assert settings["balance"] == 900.0

    logs = db.get_logs(user_id)
    assert any("[Scheduler Poll]" in l["message"] and "SUCCESS" in l["message"] for l in logs)


@pytest.mark.asyncio
async def test_poll_pending_payouts_resolves_failed(db):
    """A PENDING payout should be marked FAILED when gateway says so, with NO balance deduction."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, mode="sandbox")

    tracking_id = "track_fail_001"
    payout_id = db.create_payout(
        user_id=user_id,
        payout_date="2026-06-25",
        amount=100.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id=tracking_id,
        originator_conversation_id=tracking_id
    )
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE payouts SET created_at = ? WHERE id = ?", (old_ts, payout_id))
    conn.commit()

    mock_payout_status = AsyncMock(return_value={"status": "FAILED", "tracking_id": tracking_id})
    with patch("app.services.scheduler.check_payout_status", mock_payout_status):
        await poll_pending_payouts(db)

    payout = db.get_payout_by_conversation_id(tracking_id)
    assert payout["status"] == "FAILED"
    assert "Gateway confirmed FAILED" in payout["error_message"]

    # Balance should NOT have been deducted
    settings = db.get_settings(user_id)
    assert settings["balance"] == 1000.0


@pytest.mark.asyncio
async def test_poll_pending_payouts_ignores_no_conversation_id(db):
    """A PENDING payout without a conversation_id should not be polled."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, mode="sandbox")

    payout_id = db.create_payout(
        user_id=user_id,
        payout_date="2026-06-25",
        amount=100.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id="",  # No tracking ID yet
        originator_conversation_id=""
    )
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE payouts SET created_at = ? WHERE id = ?", (old_ts, payout_id))
    conn.commit()

    mock_payout_status = AsyncMock(return_value={"status": "SUCCESS"})
    with patch("app.services.scheduler.check_payout_status", mock_payout_status):
        await poll_pending_payouts(db)

    # Should not have been called — SQL filters conversation_id != ''
    mock_payout_status.assert_not_called()

    # Payout should remain PENDING
    payouts = db.get_payouts(user_id)
    assert payouts[0]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_poll_pending_payouts_gateway_error_leaves_pending(db):
    """If the gateway throws an exception, the payout stays PENDING."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, mode="sandbox")

    tracking_id = "track_error_001"
    payout_id = db.create_payout(
        user_id=user_id,
        payout_date="2026-06-25",
        amount=100.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id=tracking_id,
        originator_conversation_id=tracking_id
    )
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE payouts SET created_at = ? WHERE id = ?", (old_ts, payout_id))
    conn.commit()

    mock_payout_status = AsyncMock(side_effect=Exception("API unreachable"))
    with patch("app.services.scheduler.check_payout_status", mock_payout_status):
        await poll_pending_payouts(db)

    payout = db.get_payout_by_conversation_id(tracking_id)
    assert payout["status"] == "PENDING"
    assert db.get_settings(user_id)["balance"] == 1000.0


@pytest.mark.asyncio
async def test_poll_pending_payouts_still_pending_from_gateway(db):
    """If gateway returns PENDING, the payout should remain PENDING without any side effects."""
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, mode="sandbox")

    tracking_id = "track_still_pending_001"
    payout_id = db.create_payout(
        user_id=user_id,
        payout_date="2026-06-25",
        amount=100.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id=tracking_id,
        originator_conversation_id=tracking_id
    )
    conn = db.connection
    cursor = conn.cursor()
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE payouts SET created_at = ? WHERE id = ?", (old_ts, payout_id))
    conn.commit()

    mock_payout_status = AsyncMock(return_value={"status": "PENDING", "tracking_id": tracking_id})
    with patch("app.services.scheduler.check_payout_status", mock_payout_status):
        await poll_pending_payouts(db)

    payout = db.get_payout_by_conversation_id(tracking_id)
    assert payout["status"] == "PENDING"
    assert db.get_settings(user_id)["balance"] == 1000.0
