import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession

DB_FILE = "test_budget_integer.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
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
    app.dependency_overrides.pop(get_db, None)
    db.close()

def create_authenticated_user():
    client = TestClient(app)
    client.post("/api/auth/signup", json={
        "phone_number": "254712345678",
        "password": "Str0ng!P@ssw0rd",
        "confirm_password": "Str0ng!P@ssw0rd"
    })
    login_res = client.post("/api/auth/login", json={
        "phone_number": "254712345678",
        "password": "Str0ng!P@ssw0rd"
    })
    token = login_res.cookies.get("csrf_token", "")
    return client, token

def test_post_budget_item_with_decimal_amount_returns_400():
    client, csrf_token = create_authenticated_user()
    
    # Try adding decimal float amount 450.75
    res = client.post(
        "/api/budget/items",
        json={"category": "Food", "amount": 450.75},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert res.status_code in [400, 422]

def test_post_budget_item_with_valid_integer_amount_succeeds():
    client, csrf_token = create_authenticated_user()
    
    # Add whole integer amount 500
    res = client.post(
        "/api/budget/items",
        json={"category": "Food", "amount": 500},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"

def test_lock_budget_with_decimal_item_returns_400():
    client, csrf_token = create_authenticated_user()
    
    # Attempt to lock with a decimal amount payload
    res = client.post(
        "/api/budget/lock",
        json={
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "items": [{"category": "Rent", "amount": 1000.50}]
        },
        headers={"X-CSRF-Token": csrf_token}
    )
    assert res.status_code in [400, 422]
