import pytest
import datetime
import os
from unittest.mock import AsyncMock, patch
from app.db.manager import DatabaseManager
from app.services.scheduler import check_and_trigger_payout

DB_FILE = "test_payout_diagnostics.db"

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
async def test_raise_exception_when_budget_unlocked(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00", mode="simulation")
    
    current_time = datetime.datetime(2026, 6, 18, 8, 5, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "daily budget must be locked before triggering a payout" in str(exc.value)

@pytest.mark.asyncio
async def test_raise_exception_when_daily_budget_is_zero(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, daily_budget=0.0, payout_time="08:00", mode="simulation", budget_locked_until="2026-07-01")
    
    current_time = datetime.datetime(2026, 6, 18, 8, 5, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "Daily budget must be greater than zero" in str(exc.value)

@pytest.mark.asyncio
async def test_raise_exception_before_start_date(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(
        user_id, 
        balance=1000.0, 
        daily_budget=100.0, 
        payout_time="08:00",
        start_date="2026-06-20",
        mode="simulation",
        budget_locked_until="2026-07-01"
    )
    
    current_time = datetime.datetime(2026, 6, 19, 8, 5, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "Payout schedule has not started yet" in str(exc.value)
    assert "2026-06-20" in str(exc.value)

@pytest.mark.asyncio
async def test_raise_exception_after_end_date(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(
        user_id, 
        balance=1000.0, 
        daily_budget=100.0, 
        payout_time="08:00",
        end_date="2026-06-25",
        mode="simulation",
        budget_locked_until="2026-07-01"
    )
    
    current_time = datetime.datetime(2026, 6, 26, 8, 5, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "Payout schedule has already ended" in str(exc.value)
    assert "2026-06-25" in str(exc.value)

@pytest.mark.asyncio
async def test_raise_exception_before_payout_time(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00", mode="simulation", budget_locked_until="2026-07-01")
    
    current_time = datetime.datetime(2026, 6, 18, 7, 59, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "Scheduled payout time (08:00) has not been reached yet today" in str(exc.value)

@pytest.mark.asyncio
async def test_raise_exception_when_payout_already_processed_today(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00", mode="simulation", budget_locked_until="2026-07-01")
    
    # Pre-insert payout
    db.create_payout(user_id, "2026-06-18", 100.0, "254712345678", "SUCCESS", "existing_conv")
    db.update_settings(user_id, balance=900.0)
    
    current_time = datetime.datetime(2026, 6, 18, 9, 30, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "A payout has already been processed or is pending for today" in str(exc.value)

@pytest.mark.asyncio
async def test_raise_exception_when_phone_number_missing(db):
    user_id = db.create_user("254712345678", "pass")
    # Empty phone number in settings
    db.update_settings(user_id, balance=1000.0, daily_budget=100.0, payout_time="08:00", phone_number="", mode="simulation", budget_locked_until="2026-07-01")
    
    current_time = datetime.datetime(2026, 6, 18, 8, 5, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "No recipient phone number is configured" in str(exc.value)

@pytest.mark.asyncio
async def test_raise_exception_when_balance_insufficient(db):
    user_id = db.create_user("254712345678", "pass")
    db.update_settings(user_id, balance=50.0, daily_budget=100.0, payout_time="08:00", mode="simulation", budget_locked_until="2026-07-01")
    
    current_time = datetime.datetime(2026, 6, 18, 8, 15, 0)
    
    with pytest.raises(ValueError) as exc:
        await check_and_trigger_payout(db, current_time, user_id=user_id, raise_exceptions=True)
    assert "Insufficient wallet balance" in str(exc.value)
    assert "Available: KES 50.00" in str(exc.value)
    assert "Required: KES 100.00" in str(exc.value)


def test_diagnostics_unauthenticated_returns_401():
    """Verifies that calling /api/diagnostics without authentication returns 401 Unauthorized."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/api/diagnostics")
    assert res.status_code == 401, f"Expected 401 Unauthorized, got {res.status_code}"


def test_diagnostics_authenticated_returns_sanitized_metadata(db):
    """Verifies logged-in user can access diagnostics without subprocess execution errors."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.dependencies import get_db, get_current_user_id

    user_id = db.create_user("254712345678", "pass")
    
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        client = TestClient(app)
        res = client.get("/api/diagnostics")
        assert res.status_code == 200
        data = res.json()

        assert "version" in data
        assert "commit_hash" in data
        assert "timestamp" in data
        assert data["status"] == "healthy"

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_id, None)
