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

def test_first_time_payout_phone_setup_does_not_require_stepup():
    """An email-only user setting up their initial payout phone line does not trigger step-up challenge."""
    c, user_id, email, password = _setup_client(phone_number="", email="new_email_user@example.com")
    
    # 1. Add budget item
    add_res = c.post("/api/budget/items", json={"category": "Groceries", "amount": 250})
    assert add_res.status_code == 200

    # 2. Lock budget with new initial payout phone without password/OTP
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    
    lock_res = c.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "254711223344"
    })
    assert lock_res.status_code == 200
    
    db = get_test_db()
    assert db.get_payout_phone_number(user_id) == "254711223344"
    assert db.is_budget_locked(user_id) is True

def test_locking_budget_with_same_payout_phone_does_not_require_stepup():
    """A user locking their budget with their existing already-saved phone number does not trigger step-up challenge."""
    c, user_id, email, password = _setup_client(phone_number="254799887766")
    
    # Add budget item
    add_res = c.post("/api/budget/items", json={"category": "Transport", "amount": 300})
    assert add_res.status_code == 200

    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    # Lock with the same phone (or omitted payout_phone_number)
    lock_res = c.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "254799887766"
    })
    assert lock_res.status_code == 200
    assert lock_res.json()["status"] == "success"

def test_modifying_payout_phone_without_credentials_fails_400():
    """Modifying an existing payout phone line without password and OTP must be rejected with 400 Bad Request."""
    c, user_id, email, password = _setup_client(phone_number="254712345678")
    
    add_res = c.post("/api/budget/items", json={"category": "Rent", "amount": 500})
    assert add_res.status_code == 200

    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    # Attempt to change payout line to a different number without password/OTP
    lock_res = c.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "254799999999"
    })
    assert lock_res.status_code == 400
    assert "password and 6-digit OTP" in lock_res.json()["detail"]

def test_modifying_payout_phone_with_wrong_password_fails_401():
    """Modifying an existing payout phone line with an incorrect password fails with 401 Unauthorized."""
    c, user_id, email, password = _setup_client(phone_number="254712345678", password="CorrectPassword123!")
    db = get_test_db()
    
    add_res = c.post("/api/budget/items", json={"category": "Rent", "amount": 500})
    assert add_res.status_code == 200

    # Generate valid OTP challenge
    otp = db.create_otp_challenge(email, purpose="payout_stepup", ttl_seconds=300, user_id=user_id)

    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    lock_res = c.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "254799999999",
        "password": "WrongPassword!",
        "otp_code": otp
    })
    assert lock_res.status_code == 401
    assert "Invalid password" in lock_res.json()["detail"]

def test_modifying_payout_phone_with_invalid_or_expired_otp_fails_400():
    """Modifying an existing payout phone line with an invalid or expired OTP code fails with 400 Bad Request."""
    c, user_id, email, password = _setup_client(phone_number="254712345678", password="CorrectPassword123!")
    
    add_res = c.post("/api/budget/items", json={"category": "Rent", "amount": 500})
    assert add_res.status_code == 200

    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    lock_res = c.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "254799999999",
        "password": "CorrectPassword123!",
        "otp_code": "000000"
    })
    assert lock_res.status_code == 400
    assert "Invalid or expired verification code" in lock_res.json()["detail"]

def test_modifying_payout_phone_with_valid_password_and_otp_succeeds():
    """Modifying an existing payout phone line with valid password and OTP successfully updates line, locks budget, and records audit trail."""
    c, user_id, email, password = _setup_client(phone_number="254712345678", password="CorrectPassword123!")
    db = get_test_db()
    
    add_res = c.post("/api/budget/items", json={"category": "Rent", "amount": 500})
    assert add_res.status_code == 200

    # Generate valid OTP challenge
    otp = db.create_otp_challenge(email, purpose="payout_stepup", ttl_seconds=300, user_id=user_id)

    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    lock_res = c.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "254799999999",
        "password": "CorrectPassword123!",
        "otp_code": otp
    })
    assert lock_res.status_code == 200
    assert lock_res.json()["status"] == "success"

    # Verify database persistence
    assert db.get_payout_phone_number(user_id) == "254799999999"
    assert db.is_budget_locked(user_id) is True

    # Verify audit trail entry created
    audit_logs = db.session.query(AdminAuditLog).filter(AdminAuditLog.target_id == user_id).all()
    assert len(audit_logs) >= 1
    assert any(log.action == "USER_PAYOUT_PHONE_UPDATED" for log in audit_logs)
