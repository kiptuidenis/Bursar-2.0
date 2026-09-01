import datetime
import pytest
from pydantic import ValidationError
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Budget, Wallet
from app.api.schemas import WithdrawRequest

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_deposit_unlock.db")
    db = DatabaseManager(db_file)
    db.initialize()
    yield db
    db.close()

def test_is_deposit_locked_during_active_schedule(test_db):
    """Verify that is_deposit_locked returns True during an active schedule."""
    user_id = test_db.create_user("254711111111", "securepass123")
    
    # Configure 3-day schedule from 2026-09-01 to 2026-09-03
    test_db.update_settings(
        user_id,
        balance=500,
        daily_budget=100,
        start_date="2026-09-01",
        end_date="2026-09-03",
        deposit_locked_until="2026-10-01"
    )
    
    # Day 1: 2026-09-01 -> Deposit is locked
    d1 = datetime.date(2026, 9, 1)
    assert test_db.is_deposit_locked(user_id, today=d1) is True

    # Day 3: 2026-09-03 -> Deposit is locked
    d3 = datetime.date(2026, 9, 3)
    assert test_db.is_deposit_locked(user_id, today=d3) is True

def test_is_deposit_locked_unlocked_after_schedule_ends(test_db):
    """Verify that is_deposit_locked returns False once today > end_date."""
    user_id = test_db.create_user("254722222222", "securepass123")
    
    # Configure 3-day schedule ending on 2026-09-03
    test_db.update_settings(
        user_id,
        balance=200,
        daily_budget=100,
        start_date="2026-09-01",
        end_date="2026-09-03",
        deposit_locked_until="2026-10-01"
    )
    
    # Day after schedule: 2026-09-04 -> Deposit is UNLOCKED
    d4 = datetime.date(2026, 9, 4)
    assert test_db.is_deposit_locked(user_id, today=d4) is False
    assert test_db.is_budget_locked(user_id, today=d4) is False

def test_is_deposit_not_locked_when_no_schedule_configured(test_db):
    """Verify that deposits are NOT locked when no multi-day schedule is configured."""
    user_id = test_db.create_user("254733333333", "securepass123")
    
    test_db.update_settings(
        user_id,
        balance=1000,
        start_date="",
        end_date=""
    )
    
    d_any = datetime.date(2026, 9, 15)
    assert test_db.is_deposit_locked(user_id, today=d_any) is False

def test_get_user_360_payout_phone_fallback(test_db):
    """Verify get_user_360 falls back to account phone number when payout_phone_number is empty."""
    user_id = test_db.create_user("254723367594", "securepass123")
    
    # User did not set an explicit payout_phone_number
    u360 = test_db.get_user_360(user_id)
    assert u360 is not None
    assert u360["profile"]["phone_number"] == "254723367594"
    assert u360["profile"]["payout_phone_number"] == "254723367594"

def test_withdraw_request_schema_validation():
    """Verify WithdrawRequest schema validates integer figures, boundaries, and 6-digit OTP."""
    # Valid payload
    payload = WithdrawRequest(
        amount=200,
        password="SecurePassword123!",
        otp_code="123456",
        payout_phone_number="0712345678"
    )
    assert payload.amount == 200
    assert payload.payout_phone_number == "254712345678"
    assert payload.otp_code == "123456"

    # Reject below minimum (KES 10)
    with pytest.raises(ValidationError):
        WithdrawRequest(amount=5, password="pwd", otp_code="123456")

    # Reject zero or negative
    with pytest.raises(ValidationError):
        WithdrawRequest(amount=0, password="pwd", otp_code="123456")
    with pytest.raises(ValidationError):
        WithdrawRequest(amount=-100, password="pwd", otp_code="123456")

    # Reject exceeding maximum (KES 250,000)
    with pytest.raises(ValidationError):
        WithdrawRequest(amount=300000, password="pwd", otp_code="123456")

    # Reject non-6-digit OTP
    with pytest.raises(ValidationError):
        WithdrawRequest(amount=100, password="pwd", otp_code="12345")
    with pytest.raises(ValidationError):
        WithdrawRequest(amount=100, password="pwd", otp_code="abcdef")
