import os
import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, Session as DbSession, Wallet, BudgetItem, Deposit
from app.services.email import last_sent_otp_emails
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_e2e_withdrawal_ui.db"
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

def _setup_client(phone_number="254712345678", email="e2e_withdraw@example.com", password="Str0ng!P@ssw0rd", balance=800):
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

def test_dashboard_html_contains_withdrawal_modal_and_button():
    """Verify dashboard static HTML includes withdraw button and modal elements."""
    with open("src/app/static/dashboard.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="open-withdraw-btn"' in html
    assert 'id="withdraw-modal"' in html
    assert 'id="withdraw-form"' in html
    assert 'id="withdraw-phone"' in html
    assert 'id="withdraw-amount"' in html
    assert 'id="withdraw-password"' in html
    assert 'id="withdraw-otp"' in html
    assert 'id="request-withdraw-otp-btn"' in html
    assert 'id="confirm-withdraw-submit-btn"' in html

def test_app_js_contains_withdrawal_lifecycle_and_handlers():
    """Verify app.js includes visibility rules and modal event handlers."""
    with open("src/app/static/js/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "open-withdraw-btn" in js
    assert "withdraw-modal" in js
    assert "handleRequestWithdrawalOtp" in js
    assert "/api/wallet/withdraw" in js
    assert "is_budget_locked" in js

def test_full_withdrawal_lifecycle_flow():
    """
    Test the full withdrawal lifecycle:
    1. Check initial balance (800)
    2. User requests Step-Up OTP for withdrawal (300)
    3. Valid 6-digit OTP is generated and sent to email
    4. User submits withdrawal with password and OTP
    5. Balance is updated to 500
    6. Transaction is recorded in payouts history
    """
    c, user_id = _setup_client(balance=800)

    # 1. Fetch settings
    settings_res = c.get("/api/settings")
    assert settings_res.status_code == 200
    assert settings_res.json()["balance"] == 800
    assert settings_res.json()["is_budget_locked"] is False

    # 2. Request OTP for KES 300
    otp_req = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "wallet_withdrawal",
        "amount": 300
    })
    assert otp_req.status_code == 200
    assert otp_req.json()["status"] == "success"

    otp_code = last_sent_otp_emails["e2e_withdraw@example.com"]["otp_code"]
    assert len(otp_code) == 6

    # 3. Submit withdrawal
    wd_res = c.post("/api/wallet/withdraw", json={
        "amount": 300,
        "payout_phone_number": "254712345678",
        "password": "Str0ng!P@ssw0rd",
        "otp_code": otp_code
    })
    assert wd_res.status_code == 200
    assert wd_res.json()["status"] == "success"
    assert wd_res.json()["amount"] == 300
    assert wd_res.json()["balance"] == 500

    # 4. Check updated balance in settings
    updated_settings = c.get("/api/settings").json()
    assert updated_settings["balance"] == 500

    # 5. Check payouts history contains withdrawal
    payouts_res = c.get("/api/payouts")
    assert payouts_res.status_code == 200
    payouts = payouts_res.json()
    assert len(payouts) == 1
    assert payouts[0]["amount"] == 300
    assert payouts[0]["status"] == "SUCCESS"
