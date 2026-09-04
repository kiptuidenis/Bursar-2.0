import pytest
import os
import datetime
from fastapi.testclient import TestClient
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession, AdminAuditLog, OtpCode
from app.main import app, get_db
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_api_legacy_stepup.db"
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

def _setup_legacy_phone_only_client(phone_number="254711223344", password="Str0ng!P@ssw0rd2026!"):
    c = TestClient(app)
    db = get_test_db()
    pwd_hash, salt = db._hash_password(password)
    db_user = User(
        email=None,
        password_hash=pwd_hash,
        salt=salt,
        phone_number=phone_number,
        payout_phone_number=phone_number,
        email_verified=False,
        two_factor_enabled=False
    )
    db.session.add(db_user)
    db.session.flush()
    db_settings = Settings(user_id=db_user.id, phone_number=phone_number)
    db.session.add(db_settings)
    db._commit()
    user_id = db_user.id
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, phone_number, password

def _setup_verified_email_client(phone_number="254711223344", email="verified_user@example.com", password="Str0ng!P@ssw0rd2026!"):
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

def test_legacy_phone_only_user_cannot_request_stepup_otp_without_email():
    """Legacy phone-only user without email cannot request step-up OTP."""
    c, user_id, phone, password = _setup_legacy_phone_only_client()
    
    res = c.post("/api/profile/request-stepup-otp", json={"purpose": "payout_stepup"})
    assert res.status_code == 400
    assert "verified email address" in res.json()["detail"]
    assert "link an email address in Profile first" in res.json()["detail"]

def test_legacy_phone_only_user_cannot_update_settings_phone_without_email():
    """Legacy phone-only user trying to update phone number in settings is prompted to link email."""
    c, user_id, phone, password = _setup_legacy_phone_only_client()

    res = c.post("/api/settings", json={
        "phone_number": "254799887766",
        "password": password,
        "otp_code": "123456"
    })
    assert res.status_code == 400
    assert "verified email address" in res.json()["detail"]
    assert "link an email address in Profile first" in res.json()["detail"]

def test_legacy_phone_only_user_cannot_modify_payout_phone_during_budget_lock_without_email():
    """Legacy phone-only user modifying payout line during budget lock is prompted to link email."""
    c, user_id, phone, password = _setup_legacy_phone_only_client()

    # Add a budget item first
    add_res = c.post("/api/budget/items", json={"category": "Food", "amount": 300})
    assert add_res.status_code == 200

    today_eat = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()
    tomorrow = (today_eat + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (today_eat + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    res = c.post("/api/budget/lock", json={
        "start_date": tomorrow,
        "end_date": next_week,
        "payout_phone_number": "254799887766",
        "password": password,
        "otp_code": "123456"
    })
    assert res.status_code == 400
    assert "verified email address" in res.json()["detail"]
    assert "link an email address in Profile first" in res.json()["detail"]

def test_user_with_verified_email_updates_phone_successfully():
    """User with verified email and valid password + OTP successfully updates phone number."""
    c, user_id, email, password = _setup_verified_email_client(phone_number="254711223344")
    db = get_test_db()

    otp = db.create_otp_challenge(email, purpose="payout_stepup", ttl_seconds=300, user_id=user_id)

    res = c.post("/api/settings", json={
        "phone_number": "254799887766",
        "password": password,
        "otp_code": otp
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert db.get_settings(user_id).get("phone_number") == "254799887766"
