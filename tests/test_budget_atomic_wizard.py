import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Session as DbSession, OtpCode, Wallet, BudgetItem
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token
import datetime

DB_FILE = "test_budget_atomic_wizard.db"
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
    db.session.query(BudgetItem).delete()
    db.session.query(OtpCode).delete()
    db.session.query(DbSession).delete()
    db.session.query(Settings).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db.session.commit()
    yield
    db.session.rollback()
    app.dependency_overrides.pop(get_db, None)
    db.close()

def _create_user_with_balance(balance=5000, phone="254711223344", email="atomic_budget@example.com"):
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ssw0rd2026!")
    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone, phone_number=phone)
    if balance > 0:
        db.adjust_balance(user_id, balance)

    c = TestClient(app)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, phone, email

def test_atomic_budget_lock_with_items_persists_and_locks_in_one_step():
    """Verify POST /api/budget/lock with items payload persists items, updates daily_budget, and locks budget."""
    c, user_id, phone, email = _create_user_with_balance(balance=5000)
    db = get_test_db()

    # Verify no items exist initially
    items_initial = db.get_budget_items(user_id)
    assert len(items_initial) == 0

    today_eat = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    tomorrow = (today_eat + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (today_eat + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    payload = {
        "items": [
            {"category": "Food & Meals", "amount": 300},
            {"category": "Transport", "amount": 200}
        ],
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": phone
    }

    res = c.post("/api/budget/lock", json=payload)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"

    # Verify budget items were persisted
    items_after = db.get_budget_items(user_id)
    assert len(items_after) == 2
    assert sum(int(it["amount"]) for it in items_after) == 500

    # Verify settings daily_budget recalculated to 500
    settings = db.get_settings(user_id)
    assert settings["daily_budget"] == 500
    assert db.is_budget_locked(user_id) is True

def test_atomic_budget_lock_fails_validation_leaves_database_untouched():
    """Verify that if balance is insufficient or dates are invalid, no items are saved to the database."""
    c, user_id, phone, email = _create_user_with_balance(balance=200) # Only 200 balance
    db = get_test_db()

    today_eat = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    tomorrow = (today_eat + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (today_eat + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    # Items total 500 > balance 200 -> should fail
    payload = {
        "items": [
            {"category": "Rent", "amount": 300},
            {"category": "Utilities", "amount": 200}
        ],
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": phone
    }

    res = c.post("/api/budget/lock", json=payload)
    assert res.status_code == 400
    assert "cannot be more than your deposit balance" in res.json()["detail"].lower()

    # Invariant: DB remains completely untouched
    items_after = db.get_budget_items(user_id)
    assert len(items_after) == 0
    settings = db.get_settings(user_id)
    assert settings["daily_budget"] == 0
    assert db.is_budget_locked(user_id) is False
