import os
import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, Session as DbSession, Wallet, BudgetItem, Deposit
from app.services.email import last_sent_otp_emails
from app.api.dependencies import session_manager
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
    db.session.query(DbSession).delete()
    db.session.query(BudgetItem).delete()
    db.session.query(Log).delete()
    db.session.query(Deposit).delete()
    db.session.query(Payout).delete()
    db.session.query(Settings).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db._commit()
    yield db
    app.dependency_overrides.pop(get_db, None)

def _setup_client(phone_number="254712345678", email="user@example.com", password="Str0ng!P@ssw0rd", verified=True, balance=1000):
    c = TestClient(app)
    db = get_test_db()
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    
    user = db.session.query(User).filter(User.id == user_id).first()
    user.email_verified = verified
    db.update_settings(user_id, balance=balance)
    db._commit()

    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id

def test_withdrawal_requires_verified_email():
    """User without a verified email cannot request OTP or withdraw."""
    c, user_id = _setup_client(email="unverified@example.com", verified=False, balance=500)

    # 1. Requesting OTP fails
    otp_res = c.post("/api/profile/request-stepup-otp", json={"purpose": "wallet_withdrawal", "amount": 100})
    assert otp_res.status_code == 400
    assert "verified email" in otp_res.json()["detail"].lower()

    # 2. Submitting withdrawal fails
    wd_res = c.post("/api/wallet/withdraw", json={
        "amount": 100,
        "password": "Str0ng!P@ssw0rd",
        "otp_code": "123456"
    })
    assert wd_res.status_code == 400
    assert "verified email" in wd_res.json()["detail"].lower()

def test_pre_otp_balance_and_deposit_lock_validation():
    """Pre-OTP endpoint rejects requests when balance is insufficient or deposit is locked, preventing OTP dispatch."""
    c, user_id = _setup_client(email="verified@example.com", verified=True, balance=200)
    last_sent_otp_emails.clear()

    # 1. Insufficient balance check (balance is 200, requesting 300)
    otp_res_insufficient = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "wallet_withdrawal",
        "amount": 300
    })
    assert otp_res_insufficient.status_code == 400
    assert "insufficient wallet balance" in otp_res_insufficient.json()["detail"].lower()
    assert "verified@example.com" not in last_sent_otp_emails

    # 2. Active schedule deposit lock check
    db = get_test_db()
    db.update_settings(
        user_id,
        start_date="2026-09-01",
        end_date="2026-09-05",
        deposit_locked_until="2026-09-05"
    )
    otp_res_locked = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "wallet_withdrawal",
        "amount": 100
    })
    assert otp_res_locked.status_code == 400
    assert "deposit balance is currently locked" in otp_res_locked.json()["detail"].lower()
    assert "verified@example.com" not in last_sent_otp_emails

def test_withdrawal_password_and_otp_validation():
    """Withdrawal strictly enforces password and single-use 6-digit OTP."""
    c, user_id = _setup_client(email="trader@example.com", verified=True, balance=500)

    # Dispatch valid OTP
    otp_res = c.post("/api/profile/request-stepup-otp", json={"purpose": "wallet_withdrawal", "amount": 200})
    assert otp_res.status_code == 200
    valid_otp = last_sent_otp_emails["trader@example.com"]["otp_code"]

    # 1. Wrong password fails 401
    wd_wrong_pwd = c.post("/api/wallet/withdraw", json={
        "amount": 200,
        "password": "WrongPassword!1",
        "otp_code": valid_otp
    })
    assert wd_wrong_pwd.status_code == 401
    assert "invalid password" in wd_wrong_pwd.json()["detail"].lower()

    # 2. Wrong OTP fails 400
    wd_wrong_otp = c.post("/api/wallet/withdraw", json={
        "amount": 200,
        "password": "Str0ng!P@ssw0rd",
        "otp_code": "000000"
    })
    assert wd_wrong_otp.status_code == 400
    assert "invalid or expired" in wd_wrong_otp.json()["detail"].lower()

    # 3. Valid credentials succeed 200
    wd_success = c.post("/api/wallet/withdraw", json={
        "amount": 200,
        "password": "Str0ng!P@ssw0rd",
        "otp_code": valid_otp
    })
    assert wd_success.status_code == 200
    assert wd_success.json()["status"] == "success"
    assert wd_success.json()["amount"] == 200
    assert wd_success.json()["balance"] == 300

    # 4. Reusing consumed OTP fails
    wd_reuse = c.post("/api/wallet/withdraw", json={
        "amount": 100,
        "password": "Str0ng!P@ssw0rd",
        "otp_code": valid_otp
    })
    assert wd_reuse.status_code == 400
    assert "invalid or expired" in wd_reuse.json()["detail"].lower()

def test_withdrawal_idempotency_and_ledger_recording():
    """Withdrawal records ledger payout entry, logs, and respects Idempotency-Key header."""
    c, user_id = _setup_client(email="idemp@example.com", verified=True, balance=1000)

    c.post("/api/profile/request-stepup-otp", json={"purpose": "wallet_withdrawal", "amount": 400})
    otp = last_sent_otp_emails["idemp@example.com"]["otp_code"]

    headers = {"Idempotency-Key": "req_unique_wd_9999"}
    payload = {
        "amount": 400,
        "password": "Str0ng!P@ssw0rd",
        "otp_code": otp,
        "payout_phone_number": "0722334455"
    }

    # Initial request
    res1 = c.post("/api/wallet/withdraw", json=payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["balance"] == 600
    assert res1.json()["payout_phone"] == "254722334455"

    # Replayed identical request with same idempotency key returns cached result without double debiting
    res2 = c.post("/api/wallet/withdraw", json=payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json() == res1.json()

    # Verify wallet in database is 600 (not debited twice)
    db = get_test_db()
    wallet = db.get_user_wallet(user_id)
    assert wallet.available_balance == 600

    # Verify payout ledger recorded
    payouts = db.get_payouts(user_id)
    assert len(payouts) == 1
    assert payouts[0]["amount"] == 400
    assert payouts[0]["phone_number"] == "254722334455"
    assert payouts[0]["status"] == "SUCCESS"

    # Verify logs recorded
    logs = db.get_logs(user_id)
    assert any("Wallet cash-out withdrawal" in l["message"] for l in logs)
