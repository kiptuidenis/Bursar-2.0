import os
import json
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

def test_idempotency_key_prevents_duplicate_withdrawals():
    """Verify that repeating a withdrawal with the same Idempotency-Key returns the cached response without double-debiting."""
    c, user_id, email, password = _setup_client(balance=500)
    db = get_test_db()

    otp_code = db.create_otp_challenge(email, purpose="wallet_withdrawal", ttl_seconds=300, user_id=user_id)
    idempotency_key = "unique-idemp-key-12345"

    # First request
    res1 = c.post(
        "/api/wallet/withdraw",
        json={"amount": 200, "password": password, "otp_code": otp_code},
        headers={"Idempotency-Key": idempotency_key}
    )
    assert res1.status_code == 200
    assert res1.json()["balance"] == 300

    # Repeat request with same Idempotency-Key (simulating network retry / double click)
    res2 = c.post(
        "/api/wallet/withdraw",
        json={"amount": 200, "password": password, "otp_code": otp_code},
        headers={"Idempotency-Key": idempotency_key}
    )
    assert res2.status_code == 200
    assert res2.json()["balance"] == 300  # Balance remains 300, NOT decremented to 100!

    # Final DB balance check
    settings = db.get_settings(user_id)
    assert settings["balance"] == 300

def test_sequential_withdrawals_deplete_balance_correctly():
    """Verify that sequential valid withdrawals deplete balance down to 0 and subsequent attempts fail."""
    c, user_id, email, password = _setup_client(balance=300)
    db = get_test_db()

    # 1. Withdraw 200
    otp1 = db.create_otp_challenge(email, purpose="wallet_withdrawal", ttl_seconds=300, user_id=user_id)
    res1 = c.post("/api/wallet/withdraw", json={"amount": 200, "password": password, "otp_code": otp1})
    assert res1.status_code == 200
    assert res1.json()["balance"] == 100

    # 2. Withdraw 100
    otp2 = db.create_otp_challenge(email, purpose="wallet_withdrawal", ttl_seconds=300, user_id=user_id)
    res2 = c.post("/api/wallet/withdraw", json={"amount": 100, "password": password, "otp_code": otp2})
    assert res2.status_code == 200
    assert res2.json()["balance"] == 0

    # 3. Withdraw 50 (should fail due to 0 balance)
    otp3 = db.create_otp_challenge(email, purpose="wallet_withdrawal", ttl_seconds=300, user_id=user_id)
    res3 = c.post("/api/wallet/withdraw", json={"amount": 50, "password": password, "otp_code": otp3})
    assert res3.status_code == 400
    assert "Insufficient wallet balance" in res3.json()["detail"]
