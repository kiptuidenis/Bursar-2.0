import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Session as DbSession, OtpCode, Wallet
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_profile_email_link_legacy.db"
test_db = None

def get_test_db():
    global test_db
    if test_db is None:
        test_db = DatabaseManager(DB_FILE)
        test_db.initialize()
    return test_db

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
    db = get_test_db()
    db.session.query(OtpCode).delete()
    db.session.query(DbSession).delete()
    db.session.query(Settings).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db.session.commit()
    yield
    db.session.rollback()

def _create_legacy_user_client(phone_number="254711223344", password="Str0ng!P@ssw0rd"):
    """Create a legacy user with ONLY a phone number (no email address)."""
    db = get_test_db()
    user_id = db.create_user(phone_number, password)
    
    c = TestClient(app)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, phone_number

def test_legacy_user_without_email_requests_otp_on_new_email_succeeds():
    """Verify a user without an email address receives OTP on the new email they want to link."""
    c, user_id, phone = _create_legacy_user_client("254712000001")
    db = get_test_db()

    target_email = "new_legacy_link@example.com"
    res = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "email_change",
        "new_email": target_email
    })
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"
    assert "new_legacy_link@example.com" in res_data["message"]

    # Verify OTP challenge is created on the target email
    otp_rec = db.get_otp_record(target_email, "email_change")
    assert otp_rec is not None
    assert otp_rec.user_id == user_id

def test_legacy_user_linking_email_requires_otp_and_verifies_successfully():
    """Verify submitting new email with valid OTP updates user.email and sets email_verified=True."""
    c, user_id, phone = _create_legacy_user_client("254712000002")
    db = get_test_db()

    target_email = "link_verified@example.com"
    
    # 1. Submitting new email without OTP fails
    res_no_otp = c.post("/api/profile", json={
        "email": target_email
    })
    assert res_no_otp.status_code == 400
    assert "verification code is required" in res_no_otp.json()["detail"].lower()

    # 2. Submitting with wrong OTP fails
    res_bad_otp = c.post("/api/profile", json={
        "email": target_email,
        "otp_code": "000000"
    })
    assert res_bad_otp.status_code == 400
    assert "invalid or expired" in res_bad_otp.json()["detail"].lower()

    # 3. Request OTP and submit valid OTP
    valid_otp = db.create_otp_challenge(target_email, purpose="email_change", ttl_seconds=300, user_id=user_id)
    res_ok = c.post("/api/profile", json={
        "email": target_email,
        "otp_code": valid_otp
    })
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "success"

    # Verify user record updated in database
    user = db.session.query(User).filter(User.id == user_id).first()
    assert user.email == target_email
    assert user.email_verified is True

def test_legacy_user_cannot_link_email_already_registered_by_another_user():
    """Verify linking an email that is already registered to another user is rejected (400)."""
    c, user_id, phone = _create_legacy_user_client("254712000003")
    db = get_test_db()

    # Existing user with email
    pwd_hash, salt = db._hash_password("OtherPassword123!")
    other_user_id = db.create_user_email("taken_email@example.com", pwd_hash, salt)

    # Attempt to request OTP for existing email
    res_req = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "email_change",
        "new_email": "taken_email@example.com"
    })
    assert res_req.status_code == 400
    assert "already exists" in res_req.json()["detail"].lower()

    # Attempt to save profile with existing email
    valid_otp = db.create_otp_challenge("taken_email@example.com", purpose="email_change", ttl_seconds=300, user_id=user_id)
    res_save = c.post("/api/profile", json={
        "email": "taken_email@example.com",
        "otp_code": valid_otp
    })
    assert res_save.status_code == 400
    assert "already exists" in res_save.json()["detail"].lower()
