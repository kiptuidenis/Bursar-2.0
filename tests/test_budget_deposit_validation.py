import pytest
import os
import uuid
from fastapi.testclient import TestClient
from app.db.manager import DatabaseManager
from app.main import app, get_db

DB_FILE = "test_api_multitenant.db"  # Use the same test database as test_main.py to prevent override conflicts
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

app.dependency_overrides[get_db] = get_test_db

from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession

@pytest.fixture(autouse=True)
def clean_db():
    db = get_test_db()
    db.session.query(DbSession).delete()
    db.session.query(BudgetItem).delete()
    db.session.query(Log).delete()
    db.session.query(Deposit).delete()
    db.session.query(Payout).delete()
    db.session.query(Settings).delete()
    db.session.query(User).delete()
    db._commit()
    yield

client = TestClient(app)

def test_daily_budget_cannot_exceed_balance_on_settings_update():
    # 1. Signup & login
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000021", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000021", "password": "pinpassword"})

    # Set balance to 500
    res_bal = c.post("/api/settings", json={"balance": 500.0})
    assert res_bal.status_code == 200

    # Try setting daily budget to 600 (should fail because 600 > 500)
    res_fail = c.post("/api/settings", json={"daily_budget": 600.0})
    assert res_fail.status_code == 400
    assert "cannot be more than your deposit balance" in res_fail.json()["detail"].lower()

    # Set daily budget to 400 (should succeed)
    res_ok = c.post("/api/settings", json={"daily_budget": 400.0})
    assert res_ok.status_code == 200

def test_deposit_amount_cannot_be_less_than_daily_budget():
    # 1. Signup & login
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000022", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000022", "password": "pinpassword"})

    # Setup phone number in settings so deposit is allowed
    c.post("/api/settings", json={"phone_number": "254700000022"})

    # Set daily budget to 300 (balance is 0, so this is allowed)
    res_budget = c.post("/api/settings", json={"daily_budget": 300.0})
    assert res_budget.status_code == 200

    # Try initiating deposit of 200 (less than daily budget of 300, balance is 0) -> should fail
    res_dep_fail = c.post("/api/deposit/initiate", json={"amount": 200.0})
    assert res_dep_fail.status_code == 400
    assert "cannot be less than your daily budget" in res_dep_fail.json()["detail"].lower()

    # Set balance to 250 directly in DB (simulating subsequent balance state after payouts)
    db = get_test_db()
    users = db.get_all_users()
    user_id = next(u["id"] for u in users if u["phone_number"] == "254700000022")
    db.adjust_balance(user_id, 250.0)

    # Subsequent deposit of 100 (total balance would be 350 >= 300) -> should succeed
    res_dep_ok = c.post("/api/deposit/initiate", json={"amount": 100.0})
    assert res_dep_ok.status_code == 200

    # Subsequent deposit of 30 (total balance would be 280 < 300) -> should fail
    res_dep_fail2 = c.post("/api/deposit/initiate", json={"amount": 30.0})
    assert res_dep_fail2.status_code == 400
    assert "cannot be less than your daily budget" in res_dep_fail2.json()["detail"].lower()

def test_add_budget_item_cannot_exceed_balance():
    # 1. Signup & login
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000023", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000023", "password": "pinpassword"})

    # Set balance to 500.0
    c.post("/api/settings", json={"balance": 500.0})

    # Add item of 400.0 -> should succeed
    res_item1 = c.post("/api/budget/items", json={"category": "Food", "amount": 400.0})
    assert res_item1.status_code == 200

    # Try adding another item of 200.0 (total budget would be 600 > 500) -> should fail
    res_item2_fail = c.post("/api/budget/items", json={"category": "Fare", "amount": 200.0})
    assert res_item2_fail.status_code == 400
    assert "cannot be more than your deposit balance" in res_item2_fail.json()["detail"].lower()

def test_atomic_deposit_status_updates():
    db = get_test_db()
    # Create a user and a pending deposit
    user_id = db.create_user("254700000024", "pinpassword")
    checkout_id = f"test_checkout_{uuid.uuid4().hex[:6]}"
    db.create_deposit(user_id, checkout_id, 100.0)

    # First update should succeed (PENDING -> SUCCESS)
    success1 = db.update_deposit_status(checkout_id, "SUCCESS", "RECEIPT1")
    assert success1 is True

    # Second update should fail because status is no longer PENDING
    success2 = db.update_deposit_status(checkout_id, "SUCCESS", "RECEIPT2")
    assert success2 is False
