import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.db.models import User

@pytest.fixture
def email_user_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_deposit_phone.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")
    monkeypatch.setenv("MPESA_MODE", "simulation")
    monkeypatch.setenv("INTASEND_MODE", "simulation")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # Create email-only user without phone number
    user_id = db.create_user_email(
        email="emailonly@bursar.co.ke",
        password_hash="mock_hash_for_test",
        salt="argon2"
    )
    db.close()

    with TestClient(app) as client:
        # Authenticate session
        res = client.post("/api/test/setup-session", json={"user_id": user_id})
        assert res.status_code == 200
        yield client, user_id, test_db_path

def test_deposit_email_user_with_phone_in_payload_succeeds_and_saves_profile(email_user_client):
    """Email-registered user deposits with phone number; phone is normalized, STK initiated, and profile updated."""
    client, user_id, test_db_path = email_user_client

    payload = {
        "amount": 2500,
        "phone_number": "0712345678"
    }

    res = client.post("/api/deposit/initiate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "checkout_request_id" in data

    # Verify phone was normalized and persisted to settings & user profile
    db = DatabaseManager(test_db_path)
    settings = db.get_settings(user_id)
    assert settings["phone_number"] == "254712345678"

    user = db.session.query(User).filter(User.id == user_id).first()
    assert user.phone_number == "254712345678"
    assert user.payout_phone_number == "254712345678"
    db.close()

def test_deposit_email_user_without_phone_in_payload_returns_400(email_user_client):
    """Email-only user attempting deposit without providing phone number receives descriptive 400 Bad Request."""
    client, user_id, _ = email_user_client

    payload = {
        "amount": 1500
    }

    res = client.post("/api/deposit/initiate", json=payload)
    assert res.status_code == 400
    detail = res.json().get("detail", "")
    assert "M-Pesa phone number" in detail

def test_deposit_phone_user_without_phone_in_payload_uses_saved_phone(email_user_client):
    """User with pre-configured phone number can deposit without passing phone_number in payload."""
    client, user_id, test_db_path = email_user_client

    # Pre-configure phone number
    db = DatabaseManager(test_db_path)
    db.update_settings(user_id, phone_number="254799887766")
    db.close()

    payload = {
        "amount": 1000
    }

    res = client.post("/api/deposit/initiate", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

def test_deposit_with_invalid_phone_format_rejected(email_user_client):
    """Submitting invalid phone format fails schema validation with 422 Unprocessable Entity."""
    client, _, _ = email_user_client

    payload = {
        "amount": 1000,
        "phone_number": "123456"
    }

    res = client.post("/api/deposit/initiate", json=payload)
    assert res.status_code == 422
