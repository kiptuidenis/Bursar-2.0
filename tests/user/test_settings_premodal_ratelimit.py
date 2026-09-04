import pytest
import os
import datetime
from fastapi.testclient import TestClient
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession, AdminAuditLog, OtpCode
from app.main import app, get_db
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_api_ratelimit.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

client = TestClient(app)

from app.core.limiter import limiter
from app.core import config

@pytest.fixture(autouse=True)
def clean_db():
    prev_state = limiter.enabled
    limiter.enabled = True
    limiter.reset()
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
    limiter.enabled = prev_state
    db.close()

def _setup_client(phone_number="254712345678", email="ratelimit_user@example.com", password="Str0ng!P@ssw0rd2026!"):
    c = TestClient(app)
    db = get_test_db()
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, email, password

def test_request_stepup_otp_rate_limiting_enforced():
    """Requesting step-up OTP more than 5 times per minute returns 429 Too Many Requests."""
    c, user_id, email, password = _setup_client()

    success_count = 0
    rate_limited_count = 0

    for i in range(8):
        res = c.post("/api/profile/request-stepup-otp", json={"purpose": "payout_stepup"})
        if res.status_code == 200:
            success_count += 1
        elif res.status_code == 429:
            rate_limited_count += 1

    assert success_count == 5, f"Expected 5 successful OTP dispatches, got {success_count}"
    assert rate_limited_count == 3, f"Expected 3 rate limited responses, got {rate_limited_count}"

    # Verify that database has only 1 active OTP entry (previous superseded, rate-limited requests generated 0)
    db = get_test_db()
    otp_count = db.session.query(OtpCode).filter(OtpCode.email == email).count()
    assert otp_count == 1
