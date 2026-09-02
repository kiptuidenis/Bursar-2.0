import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Integer, BigInteger

from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import Wallet, Budget, Payout, BudgetItem, Deposit
from app.core.currency import validate_kes_amount

DB_FILE = "test_integer_currency.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager


@pytest.fixture(autouse=True)
def clean_db():
    for f in (DB_FILE, DB_FILE + "-shm", DB_FILE + "-wal"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    global test_db_manager
    test_db_manager = DatabaseManager(DB_FILE)
    test_db_manager.initialize()

    app.dependency_overrides[get_db] = get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)
    if test_db_manager:
        test_db_manager.close()
        test_db_manager = None
    for f in (DB_FILE, DB_FILE + "-shm", DB_FILE + "-wal"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


def test_currency_utility_validation():
    """Verify validate_kes_amount accepts whole numbers and rejects decimal values or negatives."""
    assert validate_kes_amount(100) == 100
    assert validate_kes_amount(500.0) == 500

    with pytest.raises(ValueError, match="no decimal places"):
        validate_kes_amount(100.50)

    with pytest.raises(ValueError, match="negative"):
        validate_kes_amount(-50)


def test_model_columns_are_integer_type():
    """Verify that all monetary model columns are defined as Integer in SQLAlchemy models."""
    assert isinstance(Wallet.available_balance.type, (Integer, BigInteger))
    assert isinstance(Budget.daily_budget.type, (Integer, BigInteger))
    assert isinstance(Payout.amount.type, Integer)
    assert isinstance(BudgetItem.amount.type, Integer)
    assert isinstance(Deposit.amount.type, Integer)


from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

def _setup_auth_client(phone_number, password="Str0ng!P@ssw0rdKes"):
    client = TestClient(app)
    db = get_test_db()
    email_clean = f"user_{phone_number}@example.com"
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email_clean, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    client.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    client.cookies.set("csrf_token", csrf)
    headers = {"X-CSRF-Token": csrf}
    return client, headers

def test_api_rejects_decimal_currency_amounts():
    """Verify that API endpoints reject fractional decimal KES values with validation errors."""
    client, headers = _setup_auth_client("254711777000")

    # 1. Deposit initiate rejects 150.75
    res_dep = client.post("/api/deposit/initiate", json={"amount": 150.75}, headers=headers)
    assert res_dep.status_code in (400, 422)

    # 2. Budget item rejects 200.50
    res_budget = client.post("/api/budget/items", json={"category": "Food", "amount": 200.50}, headers=headers)
    assert res_budget.status_code in (400, 422)


def test_api_accepts_whole_integer_kes_amounts():
    """Verify that API endpoints accept positive whole integer KES amounts."""
    client, headers = _setup_auth_client("254711777111")
    db = get_test_db()

    # 1. Budget item with whole KES 200
    res_budget = client.post("/api/budget/items", json={"category": "Transport", "amount": 200}, headers=headers)
    assert res_budget.status_code == 200

    # 2. Deposit initiate with whole KES 1000
    client.post("/api/settings", json={"phone_number": "254711777111"}, headers=headers)
    res_dep = client.post("/api/deposit/initiate", json={"amount": 1000}, headers=headers)
    assert res_dep.status_code == 200
    assert isinstance(res_dep.json()["checkout_request_id"], str)

    # 3. Budget lock with whole KES budget items (balance is funded)
    user = db.get_user_by_email("user_254711777111@example.com")
    db.adjust_balance(user.id, 2000)
    res_lock = client.post("/api/budget/lock", json={"items": [{"category": "Transport", "amount": 200}]}, headers=headers)
    assert res_lock.status_code == 200
