import os
import pytest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, Session as DbSession, Wallet, BudgetItem, Deposit
from app.services.email import last_sent_otp_emails
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_wallet_concurrency.db"

def get_concurrency_test_db():
    db = DatabaseManager(DB_FILE)
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except Exception:
            pass
    init_db = DatabaseManager(DB_FILE)
    init_db.initialize()
    init_db.close()

    app.dependency_overrides[get_db] = get_concurrency_test_db
    yield
    app.dependency_overrides.pop(get_db, None)
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except Exception:
            pass

def _setup_client(phone_number="254700112233", email="concurrent@example.com", password="Str0ng!P@ssw0rd", balance=300):
    c = TestClient(app)
    db = DatabaseManager(DB_FILE)
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    
    user = db.session.query(User).filter(User.id == user_id).first()
    user.email_verified = True
    db.update_settings(user_id, balance=balance)
    db._commit()

    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    db.close()

    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, token, csrf

def test_concurrent_withdrawal_race_condition_protection():
    """
    Simulate 5 simultaneous threads attempting to withdraw KES 300 when wallet balance is only KES 300.
    With atomic debit & balance checks, exactly 1 must succeed and the other 4 must fail with 400 (Insufficient balance).
    The final wallet balance must be exactly 0, never negative.
    """
    c, user_id, token, csrf = _setup_client(balance=300)

    # Request valid OTP
    c.post("/api/profile/request-stepup-otp", json={"purpose": "wallet_withdrawal", "amount": 300})
    otp = last_sent_otp_emails["concurrent@example.com"]["otp_code"]

    def attempt_withdrawal(thread_idx):
        thread_client = TestClient(app)
        thread_client.cookies.set("session_token", token)
        thread_client.cookies.set("csrf_token", csrf)
        thread_client.headers = {"X-CSRF-Token": csrf}
        return thread_client.post("/api/wallet/withdraw", json={
            "amount": 300,
            "password": "Str0ng!P@ssw0rd",
            "otp_code": otp,
            "payout_phone_number": "0700112233"
        })

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_withdrawal, i) for i in range(5)]
        responses = [f.result() for f in futures]

    successes = [r for r in responses if r.status_code == 200]
    failures = [r for r in responses if r.status_code in (400, 429)]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 4, f"Expected 4 rejected requests, got {len(failures)}"

    verify_db = DatabaseManager(DB_FILE)
    wallet = verify_db.get_user_wallet(user_id)
    assert wallet.available_balance == 0
    verify_db.close()
