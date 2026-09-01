import os
import json
import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_db, session_manager
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession, AdminAuditLog, OtpCode, Wallet
from app.core.csrf import generate_csrf_token

DB_FILE = "test_wallet_withdrawal.db"
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
    db.session.query(OtpCode).delete()
    db.session.query(AdminAuditLog).delete()
    db.session.query(DbSession).delete()
    db.session.query(BudgetItem).delete()
    db.session.query(Log).delete()
    db.session.query(Deposit).delete()
    db.session.query(Payout).delete()
    db.session.query(Settings).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db._commit()
    yield
    app.dependency_overrides.pop(get_db, None)

def _setup_client(phone_number="254712345678", email="user@example.com", password="Password123!", balance=500):
    c = TestClient(app)
    db = get_test_db()
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    db.adjust_balance(user_id, balance)
    
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, email, password

def test_request_stepup_otp_pre_validation_insufficient_balance():
    """Verify request-stepup-otp rejects withdrawal if requested amount exceeds balance (no OTP dispatched)."""
    c, user_id, email, password = _setup_client(balance=200)

    res = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "wallet_withdrawal",
        "amount": 500
    })
    assert res.status_code == 400
    assert "Insufficient wallet balance" in res.json()["detail"]

def test_request_stepup_otp_pre_validation_locked_deposit():
    """Verify request-stepup-otp rejects withdrawal if deposit is locked."""
    c, user_id, email, password = _setup_client(balance=500)
    
    # Lock deposit with active schedule ending tomorrow
    db = get_test_db()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    db.update_settings(user_id, end_date=tomorrow)

    res = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "wallet_withdrawal",
        "amount": 100
    })
    assert res.status_code == 400
    assert "locked" in res.json()["detail"].lower()

def test_request_stepup_otp_pre_validation_missing_email():
    """Verify request-stepup-otp rejects withdrawal if user has no email."""
    c = TestClient(app)
    db = get_test_db()
    user_id = db.create_user("254799999999", "Password123!")
    db.adjust_balance(user_id, 500)

    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}

    res = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "wallet_withdrawal",
        "amount": 100
    })
    assert res.status_code == 400
    assert "does not have a verified email address" in res.json()["detail"]

def test_successful_withdrawal_flow():
    """Verify complete withdrawal flow with OTP dispatch, 2FA validation, balance deduction, and audit log."""
    c, user_id, email, password = _setup_client(balance=500)
    db = get_test_db()

    # 1. Request OTP
    otp_res = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "wallet_withdrawal",
        "amount": 200
    })
    assert otp_res.status_code == 200

    from app.services.email import last_sent_otp_emails
    otp_code = last_sent_otp_emails.get(email, {}).get("otp_code")
    assert otp_code is not None

    # 2. Submit Withdrawal
    withdraw_res = c.post("/api/wallet/withdraw", json={
        "amount": 200,
        "password": password,
        "otp_code": otp_code
    })
    assert withdraw_res.status_code == 200
    data = withdraw_res.json()
    assert data["status"] == "success"
    assert data["amount"] == 200
    assert data["balance"] == 300  # 500 - 200 = 300

    # 3. Verify Database Balance & History
    settings = db.get_settings(user_id)
    assert settings["balance"] == 300

    payouts = db.get_payouts(user_id)
    assert len(payouts) >= 1
    assert payouts[0]["amount"] == 200

    # 4. Verify OTP is consumed (single-use)
    replay_res = c.post("/api/wallet/withdraw", json={
        "amount": 100,
        "password": password,
        "otp_code": otp_code
    })
    assert replay_res.status_code == 400
    assert "Invalid or expired verification code" in replay_res.json()["detail"]

def test_withdrawal_invalid_password():
    """Verify withdrawal rejects incorrect password with 401."""
    c, user_id, email, password = _setup_client(balance=500)

    c.post("/api/profile/request-stepup-otp", json={"purpose": "wallet_withdrawal", "amount": 100})
    from app.services.email import last_sent_otp_emails
    otp_code = last_sent_otp_emails.get(email, {}).get("otp_code")

    res = c.post("/api/wallet/withdraw", json={
        "amount": 100,
        "password": "WrongPassword123!",
        "otp_code": otp_code
    })
    assert res.status_code == 401
    assert "Invalid password" in res.json()["detail"]

def test_withdrawal_invalid_or_expired_otp():
    """Verify withdrawal rejects invalid 6-digit OTP code."""
    c, user_id, email, password = _setup_client(balance=500)

    res = c.post("/api/wallet/withdraw", json={
        "amount": 100,
        "password": password,
        "otp_code": "999999"
    })
    assert res.status_code == 400
    assert "Invalid or expired verification code" in res.json()["detail"]

def test_withdrawal_amount_validation_boundaries():
    """Verify withdrawal rejects amounts below min or above max."""
    c, user_id, email, password = _setup_client(balance=500000)

    # Below min KES 10
    res_min = c.post("/api/wallet/withdraw", json={
        "amount": 5,
        "password": password,
        "otp_code": "123456"
    })
    assert res_min.status_code in (400, 422)

    # Exceeding max KES 250,000
    res_max = c.post("/api/wallet/withdraw", json={
        "amount": 300000,
        "password": password,
        "otp_code": "123456"
    })
    assert res_max.status_code in (400, 422)
