import pytest
import datetime
import os
import random
from app.db.manager import DatabaseManager
from app.services.scheduler import check_and_trigger_payout

DB_FILE = "test_insufficient_balance.db"

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
async def test_scheduler_skips_payout_and_creates_notification_when_balance_insufficient(db):
    user_id = db.create_user("254711223344", "TestPass123!")
    today_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    tomorrow_str = (today_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    end_str = (today_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    # Set up locked budget of 300 KES, but balance is only 100 KES
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(
        user_id,
        balance=100.0,
        daily_budget=300.0,
        payout_time="08:00",
        mode="simulation",
        start_date=tomorrow_str,
        end_date=end_str
    )
    db.lock_budget(user_id)
    
    # Trigger time on start_date at 08:05 AM
    payout_dt = datetime.datetime.strptime(tomorrow_str, "%Y-%m-%d").replace(hour=8, minute=5, second=0)
    
    # Background scheduler execution (raise_exceptions=False)
    triggered = await check_and_trigger_payout(db, payout_dt, user_id=user_id, raise_exceptions=False)
    assert triggered is False
    
    # Verify balance was untouched
    settings = db.get_settings(user_id)
    assert settings["balance"] == 100.0
    
    # Verify low-balance warning notification was auto-dispatched
    notifications, unread_count = db.get_notifications(user_id)
    assert unread_count == 1
    assert len(notifications) == 1
    notif = notifications[0]
    assert "Payout Skipped" in notif["title"]
    assert notif["type"] == "WARNING"
    assert notif["is_read"] is False

@pytest.mark.asyncio
async def test_manual_payout_trigger_raises_value_error_when_balance_insufficient(db):
    user_id = db.create_user("254711223355", "TestPass123!")
    today_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    tomorrow_str = (today_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    end_str = (today_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(
        user_id,
        balance=50.0,
        daily_budget=300.0,
        payout_time="08:00",
        mode="simulation",
        start_date=tomorrow_str,
        end_date=end_str
    )
    db.lock_budget(user_id)
    
    payout_dt = datetime.datetime.strptime(tomorrow_str, "%Y-%m-%d").replace(hour=8, minute=5, second=0)
    
    # Manual API trigger execution (raise_exceptions=True) -> raises ValueError
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, payout_dt, user_id=user_id, raise_exceptions=True)
    assert "insufficient" in str(exc.value).lower()

@pytest.mark.asyncio
async def test_deposit_resolves_low_balance_notification_when_balance_meets_budget(db):
    user_id = db.create_user("254711223366", "TestPass123!")
    today_dt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    tomorrow_str = (today_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    end_str = (today_dt + datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    db.add_or_update_budget_item(user_id, "Food", 300.0)
    db.update_settings(
        user_id,
        balance=100.0,
        daily_budget=300.0,
        payout_time="08:00",
        mode="simulation",
        start_date=tomorrow_str,
        end_date=end_str
    )
    db.lock_budget(user_id)
    
    payout_dt = datetime.datetime.strptime(tomorrow_str, "%Y-%m-%d").replace(hour=8, minute=5, second=0)
    
    # 1. Scheduler skips payout & creates low-balance warning notification
    await check_and_trigger_payout(db, payout_dt, user_id=user_id, raise_exceptions=False)
    _, unread_count_before = db.get_notifications(user_id)
    assert unread_count_before == 1
    
    # 2. Deposit 500 KES -> balance becomes 600 KES (>= daily budget 300 KES)
    db.adjust_balance(user_id, 500.0)
    
    # 3. Verify low-balance warning notification was automatically marked as read
    _, unread_count_after = db.get_notifications(user_id)
    assert unread_count_after == 0
