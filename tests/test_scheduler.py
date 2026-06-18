import pytest
import datetime
import os
from unittest.mock import AsyncMock, patch
from db import DatabaseManager
from mpesa import MpesaClient
from scheduler import check_and_trigger_payout

DB_FILE = "test_scheduler_multitenant.db"

@pytest.fixture
def db():
    import gc
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

@pytest.mark.asyncio
async def test_scheduler_does_not_trigger_before_scheduled_time(db):
    # Setup user
    user_id = db.create_user("254712345678", "pass")
    
    # Setup settings: Balance 1000, Budget 100, Payout at 08:00, current time 07:59
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00")
    
    current_time = datetime.datetime(2026, 6, 18, 7, 59, 0)
    mock_client = AsyncMock()
    
    triggered = await check_and_trigger_payout(db, mock_client, current_time, user_id=user_id)
    
    assert triggered is False
    assert db.get_settings(user_id)["balance"] == 1000.0
    assert len(db.get_payouts(user_id)) == 0

@pytest.mark.asyncio
async def test_scheduler_triggers_after_scheduled_time(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00")
    
    current_time = datetime.datetime(2026, 6, 18, 8, 1, 0)
    mock_client = AsyncMock()
    mock_client.send_b2c_payout.return_value = {
        "ConversationID": "mock_conv_123",
        "OriginatorConversationID": "mock_orig_123",
        "ResponseCode": "0",
        "ResponseDescription": "Success"
    }
    
    triggered = await check_and_trigger_payout(db, mock_client, current_time, user_id=user_id)
    
    assert triggered is True
    assert db.get_settings(user_id)["balance"] == 900.0
    
    payouts = db.get_payouts(user_id)
    assert len(payouts) == 1
    assert payouts[0]["payout_date"] == "2026-06-18"
    assert payouts[0]["amount"] == 100.0
    assert payouts[0]["status"] == "SUCCESS"

@pytest.mark.asyncio
async def test_scheduler_double_spend_protection(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00")
    
    # Pre-insert payout
    db.create_payout(user_id, "2026-06-18", 100.0, "254712345678", "SUCCESS", "existing_conv")
    db.update_settings(user_id, balance=900.0)
    
    current_time = datetime.datetime(2026, 6, 18, 9, 30, 0)
    mock_client = AsyncMock()
    
    triggered = await check_and_trigger_payout(db, mock_client, current_time, user_id=user_id)
    
    assert triggered is False
    assert db.get_settings(user_id)["balance"] == 900.0
    assert len(db.get_payouts(user_id)) == 1

@pytest.mark.asyncio
async def test_scheduler_insufficient_balance(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=50.0, daily_budget=100.0, payout_time="08:00")
    
    current_time = datetime.datetime(2026, 6, 18, 8, 15, 0)
    mock_client = AsyncMock()
    
    triggered = await check_and_trigger_payout(db, mock_client, current_time, user_id=user_id)
    
    assert triggered is False
    assert db.get_settings(user_id)["balance"] == 50.0
    assert len(db.get_payouts(user_id)) == 0
    
    logs = db.get_logs(user_id)
    assert any(log["level"] == "ERROR" and "insufficient" in log["message"].lower() for log in logs)

@pytest.mark.asyncio
async def test_scheduler_rollback_on_mpesa_error(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00")
    
    current_time = datetime.datetime(2026, 6, 18, 8, 5, 0)
    mock_client = AsyncMock()
    mock_client.send_b2c_payout.side_effect = Exception("Connection Timeout")
    
    triggered = await check_and_trigger_payout(db, mock_client, current_time, user_id=user_id)
    
    assert triggered is False
    assert db.get_settings(user_id)["balance"] == 1000.0  # Balance refunded
    
    payouts = db.get_payouts(user_id)
    assert len(payouts) == 1
    assert payouts[0]["status"] == "FAILED"
    assert "Connection Timeout" in payouts[0]["error_message"]
