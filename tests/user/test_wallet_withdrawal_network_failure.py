import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, Session as DbSession, Wallet, BudgetItem, Deposit
from app.services.email import last_sent_otp_emails
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_wallet_network_fail.db"
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

def _setup_client(phone_number="254799999999", email="refund@example.com", password="Str0ng!P@ssw0rd", balance=500):
    c = TestClient(app)
    db = get_test_db()
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    
    user = db.session.query(User).filter(User.id == user_id).first()
    user.email_verified = True
    db.update_settings(user_id, balance=balance)
    db._commit()

    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id

def test_withdrawal_gateway_network_timeout_auto_refunds_balance():
    """When payment gateway throws a network timeout or error, wallet balance is automatically refunded."""
    c, user_id = _setup_client(balance=500)

    c.post("/api/profile/request-stepup-otp", json={"purpose": "wallet_withdrawal", "amount": 200})
    otp = last_sent_otp_emails["refund@example.com"]["otp_code"]

    with patch("app.api.routers.wallet.send_b2c_payout", side_effect=Exception("Gateway Connection Timeout")):
        res = c.post("/api/wallet/withdraw", json={
            "amount": 200,
            "password": "Str0ng!P@ssw0rd",
            "otp_code": otp,
            "payout_phone_number": "0799999999"
        })

    assert res.status_code == 502
    assert "refunded" in res.json()["detail"].lower()

    # Verify wallet balance in DB is still 500
    db = get_test_db()
    wallet = db.get_user_wallet(user_id)
    assert wallet.available_balance == 500

    # Verify error log recorded
    logs = db.get_logs(user_id)
    assert any("failed" in l["message"].lower() and "refunded" in l["message"].lower() for l in logs)
