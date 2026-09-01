import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, BudgetItem, Session as DbSession, Wallet
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_budget_zero_balance_invariants.db"
test_db = None

def get_test_db():
    global test_db
    if test_db is None:
        test_db = DatabaseManager(DB_FILE)
        test_db.initialize()
    return test_db

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
    db = get_test_db()
    db.session.query(DbSession).delete()
    db.session.query(BudgetItem).delete()
    db.session.query(Settings).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db._commit()
    yield db
    app.dependency_overrides.pop(get_db, None)

def _setup_user(email="zero_balance_user@example.com", balance=0):
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user_id = db.create_user_email(
        email=email,
        password_hash=pwd_hash,
        salt=salt,
        phone_number="254711999888",
        payout_phone="254711999888"
    )
    user = db.session.query(User).filter(User.id == user_id).first()
    user.email_verified = True
    db.update_settings(user_id, balance=balance)
    db._commit()

    c = TestClient(app)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id

def test_locking_budget_with_zero_balance_fails():
    """Users cannot schedule or lock a budget with zero wallet balance."""
    c, user_id = _setup_user(balance=0)
    db = get_test_db()

    # Add draft items
    db.session.add(BudgetItem(user_id=user_id, category="Food", amount=300))
    db._commit()
    db.recalculate_daily_budget(user_id)

    # Attempt to lock with zero balance
    res = c.post("/api/budget/lock", json={
        "start_date": "2026-09-05",
        "end_date": "2026-09-25"
    })
    assert res.status_code == 400
    assert "zero wallet balance" in res.json()["detail"].lower()
    assert db.is_budget_locked(user_id) is False

def test_daily_budget_exceeding_wallet_balance_rejected():
    """Setting daily budget greater than wallet balance is rejected."""
    c, user_id = _setup_user(balance=500)
    db = get_test_db()

    res = c.post("/api/settings", json={"daily_budget": 1000})
    assert res.status_code == 400
    assert "cannot exceed" in res.json()["detail"].lower()

def test_locking_budget_with_sufficient_balance_succeeds():
    """Users with sufficient balance can lock budget successfully."""
    c, user_id = _setup_user(balance=5000)
    db = get_test_db()

    db.session.add(BudgetItem(user_id=user_id, category="Groceries", amount=500))
    db._commit()
    db.recalculate_daily_budget(user_id)

    res = c.post("/api/budget/lock", json={
        "start_date": "2026-09-05",
        "end_date": "2026-09-25"
    })
    assert res.status_code == 200
    assert db.is_budget_locked(user_id) is True
    assert db.is_deposit_locked(user_id) is True

def test_depleted_balance_auto_unlocks_budget_and_deposit():
    """
    When user runs out of funds (balance reaches zero), budget and deposit locks
    automatically lift so the user can reconfigure a new budget upon depositing.
    """
    c, user_id = _setup_user(balance=3000)
    db = get_test_db()

    # 1. Lock budget schedule
    db.session.add(BudgetItem(user_id=user_id, category="Rent", amount=300))
    db._commit()
    db.recalculate_daily_budget(user_id)

    res = c.post("/api/budget/lock", json={
        "start_date": "2026-09-05",
        "end_date": "2026-09-25"
    })
    assert res.status_code == 200
    assert db.is_budget_locked(user_id) is True
    assert db.is_deposit_locked(user_id) is True

    # 2. Simulate payouts exhausting user balance to 0
    db.adjust_balance(user_id, -3000)
    wallet = db.get_user_wallet(user_id)
    assert wallet.available_balance == 0

    # 3. Verify locks are automatically lifted
    assert db.is_budget_locked(user_id) is False
    assert db.is_deposit_locked(user_id) is False

    # 4. Verify /api/settings reports unlocked state
    settings_res = c.get("/api/settings")
    assert settings_res.status_code == 200
    assert settings_res.json()["is_budget_locked"] is False
    assert settings_res.json()["is_deposit_locked"] is False

    # 5. Verify user can mutate budget items without being blocked by lock
    items_res = c.post("/api/budget/items", json={
        "category": "New Month Plan",
        "amount": 200
    })
    assert items_res.status_code == 200
    assert items_res.json()["status"] == "success"
