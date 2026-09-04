import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.db.models import User

@pytest.fixture
def user_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_budget_payout.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # Create email-only user without any phone number
    user_id = db.create_user_email(
        email="budgetuser@bursar.co.ke",
        password_hash="mock_hash_budget",
        salt="argon2"
    )
    # Add initial balance and a budget item
    db.adjust_balance(user_id, 10000)
    db.add_or_update_budget_item(user_id, "Daily Allowance", 500)
    db.close()

    with TestClient(app) as client:
        res = client.post("/api/test/setup-session", json={"user_id": user_id})
        assert res.status_code == 200
        yield client, user_id, test_db_path

def _get_test_dates():
    today_eat = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()
    tomorrow = (today_eat + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (today_eat + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    return tomorrow, next_week

def test_lock_budget_without_payout_phone_when_none_configured_returns_400(user_client):
    """Attempting to lock budget without a payout phone when none is configured returns 400 Bad Request."""
    client, user_id, _ = user_client
    tomorrow, next_week = _get_test_dates()

    res = client.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week
    })
    assert res.status_code == 400
    assert "phone number is required" in res.json().get("detail", "").lower()

def test_lock_budget_with_payout_phone_sets_payout_destination_and_locks(user_client):
    """Providing payout_phone_number during budget lock sets the payout destination and locks the budget."""
    client, user_id, test_db_path = user_client
    tomorrow, next_week = _get_test_dates()

    res = client.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "0712345678"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["budget_locked_until"]

    # Verify payout phone was set on User and Settings
    db = DatabaseManager(test_db_path)
    user = db.session.query(User).filter(User.id == user_id).first()
    assert user.payout_phone_number == "254712345678"
    settings = db.get_settings(user_id)
    assert settings["phone_number"] == "254712345678"
    assert db.is_budget_locked(user_id)
    db.close()

def test_lock_budget_with_existing_payout_phone_succeeds_without_reproviding(user_client):
    """User with an already configured payout phone can lock budget without re-providing payout_phone_number."""
    client, user_id, test_db_path = user_client

    # Pre-configure payout phone
    db = DatabaseManager(test_db_path)
    db.update_payout_phone_number(user_id, "254799887766")
    db.close()

    tomorrow, next_week = _get_test_dates()

    res = client.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"
