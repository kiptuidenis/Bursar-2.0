import pytest
import datetime
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Session as DbSession, Wallet, Budget
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_settings_phone_formats.db"
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

def _setup_client(phone_number="", email="", password="Str0ng!P@ssw0rd2026!"):
    c = TestClient(app)
    db = get_test_db()
    phone_clean = phone_number or ""
    email_clean = email or (f"user_{phone_number}@example.com" if phone_number else f"user_{datetime.datetime.now().microsecond}@example.com")
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email_clean, pwd_hash, salt, payout_phone=phone_clean, phone_number=phone_clean)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, email_clean, password

def test_settings_accepts_and_normalizes_various_phone_formats():
    """Verify that settings phone number accepts 07..., 01..., +254..., and 254... and normalizes them."""
    test_cases = [
        ("0712345678", "254712345678"),
        ("0112345678", "254112345678"),
        ("+254712345678", "254712345678"),
        ("+254112345678", "254112345678"),
        ("254712345678", "254712345678"),
        ("254112345678", "254112345678"),
    ]

    for idx, (input_phone, expected_normalized) in enumerate(test_cases):
        c, user_id, email, pwd = _setup_client(phone_number="", email=f"test_phone_{idx}_{datetime.datetime.now().microsecond}@example.com")
        res = c.post("/api/settings", json={"phone_number": input_phone})
        assert res.status_code == 200, f"Expected {input_phone} to be accepted, got {res.status_code}: {res.text}"
        
        db = get_test_db()
        settings = db.get_settings(user_id)
        assert settings.get("phone_number") == expected_normalized

def test_settings_rejects_invalid_phone_formats():
    """Verify that non-Safaricom or invalid length numbers are rejected with HTTP 400."""
    c, user_id, email, pwd = _setup_client(phone_number="", email="invalid_phone_user@example.com")

    invalid_phones = [
        "0201234567",   # Landline prefix 020
        "12345",        # Too short
        "071234567",     # 9 digits instead of 10
        "071234567890",  # Too long
        "+14155552671", # US phone number
        "254812345678", # Non-supported prefix 8
        "abcdefghij",   # Non-numeric
    ]

    for inv in invalid_phones:
        res = c.post("/api/settings", json={"phone_number": inv})
        assert res.status_code == 400, f"Expected {inv} to be rejected"
        assert "invalid safaricom phone number" in res.json()["detail"].lower()

def test_formatting_variation_of_same_phone_does_not_require_stepup():
    """Submitting the same telephone number in a different format (e.g. 07... instead of 254...) does not require step-up OTP."""
    c, user_id, email, pwd = _setup_client(phone_number="254711223344", email="same_phone_format@example.com")
    
    # User currently has 254711223344; submits 0711223344
    res = c.post("/api/settings", json={"phone_number": "0711223344"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    # Submits with leading +254
    res2 = c.post("/api/settings", json={"phone_number": "+254711223344"})
    assert res2.status_code == 200
    assert res2.json()["status"] == "success"
