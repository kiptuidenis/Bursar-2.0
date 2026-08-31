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

def test_deposit_with_custom_phone_succeeds_without_modifying_profile_or_settings(email_user_client):
    """Email-registered user deposits with phone number; STK push succeeds, but profile/payout phone is NOT modified."""
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

    # Verify phone was NOT written to settings, user profile, or payout phone
    db = DatabaseManager(test_db_path)
    settings = db.get_settings(user_id)
    assert not settings.get("phone_number")

    user = db.session.query(User).filter(User.id == user_id).first()
    assert not user.phone_number
    assert not user.payout_phone_number
    db.close()

def test_deposit_with_duplicate_phone_succeeds_and_leaves_both_users_unchanged(email_user_client):
    """Depositing from a phone already registered to another account succeeds and leaves both profiles untouched."""
    client, user_id, test_db_path = email_user_client

    db = DatabaseManager(test_db_path)
    user2_id = db.create_user_email(
        email="otheruser@bursar.co.ke",
        password_hash="mock_hash_2",
        salt="argon2",
        phone_number="254799000111"
    )
    db.update_payout_phone_number(user2_id, "254799000111")
    db.close()

    # User 1 deposits using User 2's phone
    payload = {
        "amount": 3000,
        "phone_number": "0799000111"
    }

    res = client.post("/api/deposit/initiate", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Verify User 2's profile is intact
    db = DatabaseManager(test_db_path)
    u2 = db.session.query(User).filter(User.id == user2_id).first()
    assert u2.phone_number == "254799000111"
    assert u2.payout_phone_number == "254799000111"

    # Verify User 1's profile is still empty
    u1 = db.session.query(User).filter(User.id == user_id).first()
    assert not u1.phone_number
    assert not u1.payout_phone_number
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
