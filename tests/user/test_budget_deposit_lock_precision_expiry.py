import datetime
import pytest
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Budget, Wallet

DB_FILE = "test_precision_expiry.db"
test_db = None

def get_test_db():
    global test_db
    if test_db is None:
        test_db = DatabaseManager(DB_FILE)
        test_db.initialize()
    return test_db

@pytest.fixture(autouse=True)
def clean_db():
    db = get_test_db()
    db.session.query(Budget).delete()
    db.session.query(Settings).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db.session.commit()
    yield
    db.session.rollback()

def test_budget_and_deposit_lock_precision_expiry_at_payout_time():
    """
    Test that budget lock and deposit lock end on the last day of the schedule
    after the time of the last disbursement (payout_time) has passed.
    """
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user_id = db.create_user_email("precision_user@example.com", pwd_hash, salt)

    # Deposit funds to have positive balance
    db.adjust_balance(user_id, 10000)

    # Configure schedule with end_date = 2026-09-02 and payout_time = 08:00
    db.update_settings(
        user_id=user_id,
        daily_budget=500,
        start_date="2026-08-01",
        end_date="2026-09-02",
        total_days=33,
        payout_time="08:00"
    )

    eat_tz = datetime.timezone(datetime.timedelta(hours=3))

    # Case 1: On end_date (2026-09-02) at 07:59 AM EAT (before payout_time 08:00) -> Still LOCKED
    now_before = datetime.datetime(2026, 9, 2, 7, 59, 0, tzinfo=eat_tz)
    assert db.is_budget_locked(user_id, now=now_before) is True
    assert db.is_deposit_locked(user_id, now=now_before) is True

    # Case 2: On end_date (2026-09-02) at 08:00 AM EAT (at payout_time 08:00) -> UNLOCKED
    now_at = datetime.datetime(2026, 9, 2, 8, 0, 0, tzinfo=eat_tz)
    assert db.is_budget_locked(user_id, now=now_at) is False
    assert db.is_deposit_locked(user_id, now=now_at) is False

    # Case 3: On end_date (2026-09-02) at 08:30 AM EAT (after payout_time 08:00) -> UNLOCKED
    now_after = datetime.datetime(2026, 9, 2, 8, 30, 0, tzinfo=eat_tz)
    assert db.is_budget_locked(user_id, now=now_after) is False
    assert db.is_deposit_locked(user_id, now=now_after) is False

def test_budget_and_deposit_lock_future_and_past_dates():
    """
    Test lock behavior when current date is strictly before or strictly after end_date.
    """
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user_id = db.create_user_email("precision_dates@example.com", pwd_hash, salt)

    db.adjust_balance(user_id, 10000)
    db.update_settings(
        user_id=user_id,
        daily_budget=500,
        start_date="2026-09-01",
        end_date="2026-09-10",
        total_days=10,
        payout_time="10:00"
    )

    eat_tz = datetime.timezone(datetime.timedelta(hours=3))

    # Mid-schedule on 2026-09-05 at 11:00 AM (past payout time for that day, but before schedule end date) -> LOCKED
    now_mid = datetime.datetime(2026, 9, 5, 11, 0, 0, tzinfo=eat_tz)
    assert db.is_budget_locked(user_id, now=now_mid) is True
    assert db.is_deposit_locked(user_id, now=now_mid) is True

    # After schedule on 2026-09-11 at 06:00 AM -> UNLOCKED
    now_past = datetime.datetime(2026, 9, 11, 6, 0, 0, tzinfo=eat_tz)
    assert db.is_budget_locked(user_id, now=now_past) is False
    assert db.is_deposit_locked(user_id, now=now_past) is False

def test_explicit_lock_until_precision_expiry():
    """
    Test explicit deposit_locked_until and budget_locked_until precision expiry.
    """
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user_id = db.create_user_email("precision_explicit@example.com", pwd_hash, salt)

    db.adjust_balance(user_id, 10000)
    db.update_settings(
        user_id=user_id,
        budget_locked_until="2026-09-02",
        deposit_locked_until="2026-09-02",
        payout_time="09:30"
    )

    eat_tz = datetime.timezone(datetime.timedelta(hours=3))

    # Before 09:30 AM on 2026-09-02 -> LOCKED
    now_before = datetime.datetime(2026, 9, 2, 9, 15, 0, tzinfo=eat_tz)
    assert db.is_budget_locked(user_id, now=now_before) is True
    assert db.is_deposit_locked(user_id, now=now_before) is True

    # At or after 09:30 AM on 2026-09-02 -> UNLOCKED
    now_after = datetime.datetime(2026, 9, 2, 9, 31, 0, tzinfo=eat_tz)
    assert db.is_budget_locked(user_id, now=now_after) is False
    assert db.is_deposit_locked(user_id, now=now_after) is False
