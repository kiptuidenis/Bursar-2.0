import pytest
from sqlalchemy import inspect
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import Settings, Wallet, Budget, User, Session as DbSession

DB_FILE = "test_settings_domain_decoupling.db"
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
    db.session.query(Settings).delete()
    db.session.query(Budget).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db.session.commit()
    yield
    db.session.rollback()
    app.dependency_overrides.pop(get_db, None)
    db.close()

from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

def _create_user_client(phone="254711998877", password="TestPassword123!"):
    db = get_test_db()
    user_id = db.create_user(phone, password)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    client = TestClient(app)
    client.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    client.cookies.set("csrf_token", csrf)
    client.headers = {"X-CSRF-Token": csrf}
    return client, user_id

def test_settings_orm_model_has_no_financial_columns():
    """Verify Settings table schema does NOT possess balance or daily_budget columns."""
    db = get_test_db()
    inspector = inspect(db.engine)
    settings_cols = [c["name"] for c in inspector.get_columns("settings")]
    
    assert "balance" not in settings_cols, "balance column must not exist in settings table"
    assert "daily_budget" not in settings_cols, "daily_budget column must not exist in settings table"
    
    # Verify Wallet and Budget models own their respective domains
    wallet_cols = [c["name"] for c in inspector.get_columns("wallets")]
    assert "available_balance" in wallet_cols
    
    budget_cols = [c["name"] for c in inspector.get_columns("budgets")]
    assert "daily_budget" in budget_cols

def test_settings_update_api_rejects_balance_and_daily_budget_injection():
    """Verify POST /api/settings cannot be used to inject or alter financial or budget amounts."""
    client, user_id = _create_user_client()
    db = get_test_db()
    db.adjust_balance(user_id, 3000)
    db.recalculate_daily_budget(user_id)

    # Attempt to post daily_budget to /api/settings
    res = client.post("/api/settings", json={"daily_budget": 9999})
    assert res.status_code == 400
    
    # Verify wallet and budget in database remain unaffected
    wallet = db.get_user_wallet(user_id)
    budget = db.get_user_budget(user_id)
    assert wallet.available_balance == 3000
    assert budget.daily_budget == 0

def test_settings_update_api_accepts_valid_configuration_fields():
    """Verify POST /api/settings accepts preferences and valid configurations."""
    client, user_id = _create_user_client()
    
    res = client.post("/api/settings", json={"mode": "sandbox", "mpesa_shortcode": "600000"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    db = get_test_db()
    settings = db.get_settings(user_id)
    assert settings["mode"] == "sandbox"
    assert settings["mpesa_shortcode"] == "600000"
