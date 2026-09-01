import os
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

def test_gateway_network_timeout_triggers_auto_refund(monkeypatch):
    """Verify that payment gateway exceptions automatically refund the user's wallet balance."""
    c, user_id, email, password = _setup_client(balance=500)
    db = get_test_db()

    otp_code = db.create_otp_challenge(email, purpose="wallet_withdrawal", ttl_seconds=300, user_id=user_id)

    # Mock gateway failure
    async def mock_failed_b2c(*args, **kwargs):
        raise Exception("Safaricom B2C Gateway Connection Timeout (504)")

    monkeypatch.setattr("app.api.routers.wallet.send_b2c_payout", mock_failed_b2c)

    res = c.post("/api/wallet/withdraw", json={
        "amount": 200,
        "password": password,
        "otp_code": otp_code
    })
    assert res.status_code == 502
    assert "refunded" in res.json()["detail"].lower()

    # Verify balance was NOT lost and is intact at 500
    settings = db.get_settings(user_id)
    assert settings["balance"] == 500

    # Verify error log was recorded
    logs = db.get_logs(user_id)
    error_logs = [l for l in logs if l["level"] == "ERROR"]
    assert len(error_logs) >= 1
    assert "refunded" in error_logs[0]["message"].lower()
