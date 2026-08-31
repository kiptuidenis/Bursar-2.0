import pytest
import os
import datetime
from fastapi.testclient import TestClient
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession, AdminAuditLog, OtpCode
from app.main import app, get_db
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_api_multitenant.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
    client.cookies.clear()
    db = get_test_db()
    db.session.query(OtpCode).delete()
    db.session.query(AdminAuditLog).delete()
    db.session.query(DbSession).delete()
    db.session.query(BudgetItem).delete()
    db.session.query(Log).delete()
    db.session.query(Deposit).delete()
    db.session.query(Payout).delete()
    db.session.query(Settings).delete()
    db.session.query(User).delete()
    db._commit()
    yield
    client.cookies.clear()
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

def test_initial_phone_setup_in_settings_does_not_require_stepup():
    """An email-only user setting their initial phone number in settings does not trigger step-up challenge."""
    c, user_id, email, password = _setup_client(phone_number="", email="email_only_user@example.com")
    
    res = c.post("/api/settings", json={
        "phone_number": "254711223344"
    })
    assert res.status_code == 200
    db = get_test_db()
    assert db.get_settings(user_id).get("phone_number") == "254711223344"

def test_updating_non_phone_settings_does_not_require_stepup():
    """Updating payout time or daily budget with unchanged phone number does not trigger step-up challenge."""
    c, user_id, email, password = _setup_client(phone_number="254712345678")
    
    res = c.post("/api/settings", json={
        "phone_number": "254712345678",
        "mpesa_shortcode": "600123"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"

def test_modifying_phone_number_in_settings_without_credentials_fails_400():
    """Modifying an existing configured phone number in settings without password and OTP must return 400 Bad Request."""
    c, user_id, email, password = _setup_client(phone_number="254712345678")
    
    res = c.post("/api/settings", json={
        "phone_number": "254799887766"
    })
    assert res.status_code == 400
    assert "password and 6-digit OTP" in res.json()["detail"]

def test_modifying_phone_number_in_settings_with_wrong_password_fails_401():
    """Modifying an existing phone number in settings with an invalid password returns 401 Unauthorized."""
    c, user_id, email, password = _setup_client(phone_number="254712345678", password="CorrectPass123!")
    db = get_test_db()
    
    otp = db.create_otp_challenge(email, purpose="payout_stepup", ttl_seconds=300, user_id=user_id)
    
    res = c.post("/api/settings", json={
        "phone_number": "254799887766",
        "password": "WrongPassword!",
        "otp_code": otp
    })
    assert res.status_code == 401
    assert "Invalid password" in res.json()["detail"]

def test_modifying_phone_number_in_settings_with_invalid_otp_fails_400():
    """Modifying an existing phone number in settings with an invalid OTP code returns 400 Bad Request."""
    c, user_id, email, password = _setup_client(phone_number="254712345678", password="CorrectPass123!")
    
    res = c.post("/api/settings", json={
        "phone_number": "254799887766",
        "password": "CorrectPass123!",
        "otp_code": "000000"
    })
    assert res.status_code == 400
    assert "Invalid or expired verification code" in res.json()["detail"]

def test_modifying_phone_number_in_settings_with_valid_password_and_otp_succeeds():
    """Modifying an existing phone number with valid password and OTP updates settings and logs security audit trail."""
    c, user_id, email, password = _setup_client(phone_number="254712345678", password="CorrectPass123!")
    db = get_test_db()
    
    otp = db.create_otp_challenge(email, purpose="payout_stepup", ttl_seconds=300, user_id=user_id)
    
    res = c.post("/api/settings", json={
        "phone_number": "254799887766",
        "password": "CorrectPass123!",
        "otp_code": otp
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    assert db.get_settings(user_id).get("phone_number") == "254799887766"
    
    # Audit log check
    audit_logs = db.session.query(AdminAuditLog).filter(AdminAuditLog.target_id == user_id).all()
    assert len(audit_logs) >= 1
    assert any(log.action == "USER_PHONE_UPDATED" for log in audit_logs)
