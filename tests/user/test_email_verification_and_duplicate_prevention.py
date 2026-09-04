import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Session as DbSession, OtpCode
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_email_verification_and_duplicates.db"
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
    db.session.query(User).delete()
    db._commit()
    yield db
    app.dependency_overrides.pop(get_db, None)

def test_db_create_user_email_enforces_uniqueness():
    """Test that DatabaseManager.create_user_email rejects duplicate emails."""
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    db.create_user_email("user1@example.com", pwd_hash, salt)

    with pytest.raises(ValueError, match="already exists"):
        db.create_user_email("user1@example.com", pwd_hash, salt)

def test_signup_api_rejects_existing_email():
    """Test POST /api/auth/signup rejects registration with an existing email."""
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    db.create_user_email("existing@example.com", pwd_hash, salt)

    c = TestClient(app)
    res = c.post("/api/auth/signup", json={
        "email": "existing@example.com",
        "password": "Str0ng!P@ss2026"
    })
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"].lower()

def test_verify_otp_signup_rejects_existing_email():
    """Test POST /api/auth/verify-otp for signup_2fa rejects if account was created in meantime."""
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    otp_code = db.create_otp_challenge(
        "race@example.com",
        purpose="signup_2fa",
        ttl_seconds=300,
        password_hash=f"{pwd_hash}:{salt}"
    )

    # Simulate existing account creation
    db.create_user_email("race@example.com", pwd_hash, salt)

    c = TestClient(app)
    res = c.post("/api/auth/verify-otp", json={
        "email": "race@example.com",
        "otp_code": otp_code,
        "purpose": "signup_2fa"
    })
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"].lower()

def test_profile_update_same_email_does_not_require_otp():
    """Test that updating name/bio with unchanged email succeeds without OTP."""
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user_id = db.create_user_email("alice@example.com", pwd_hash, salt)

    c = TestClient(app)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}

    res = c.post("/api/profile", json={
        "first_name": "Alice",
        "last_name": "Wonderland",
        "email": "alice@example.com",
        "bio": "Updated bio"
    })
    assert res.status_code == 200
    data = res.json()["profile"]
    assert data["first_name"] == "Alice"
    assert data["email"] == "alice@example.com"

def test_profile_update_duplicate_email_rejected():
    """Test that changing email to another registered user's email is rejected."""
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user1_id = db.create_user_email("user1@example.com", pwd_hash, salt)
    user2_id = db.create_user_email("user2@example.com", pwd_hash, salt)

    c = TestClient(app)
    token = session_manager.create_session(user1_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}

    # Request OTP for already-taken email
    otp_res = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "email_change",
        "new_email": "user2@example.com"
    })
    assert otp_res.status_code == 400
    assert "already exists" in otp_res.json()["detail"].lower()

    # Try direct profile update to already-taken email
    res = c.post("/api/profile", json={
        "first_name": "User",
        "last_name": "One",
        "email": "user2@example.com",
        "otp_code": "123456"
    })
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"].lower()

def test_profile_update_email_change_requires_and_verifies_otp():
    """Test that changing email requires valid OTP sent to original registered email address."""
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user_id = db.create_user_email("old_email@example.com", pwd_hash, salt)

    c = TestClient(app)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}

    # Attempt to change email without OTP
    res_no_otp = c.post("/api/profile", json={
        "first_name": "Old",
        "last_name": "User",
        "email": "new_email@example.com"
    })
    assert res_no_otp.status_code == 400
    assert "verification code is required" in res_no_otp.json()["detail"].lower()

    # Request OTP for changing to new email -> Dispatched to current original email
    req_otp = c.post("/api/profile/request-stepup-otp", json={
        "purpose": "email_change",
        "new_email": "new_email@example.com"
    })
    assert req_otp.status_code == 200
    assert "old_email@example.com" in req_otp.json()["message"]

    # Retrieve created OTP on original email
    otp_rec = db.get_otp_record("old_email@example.com", "email_change")
    assert otp_rec is not None

    # Submit with invalid OTP
    res_bad_otp = c.post("/api/profile", json={
        "first_name": "Old",
        "last_name": "User",
        "email": "new_email@example.com",
        "otp_code": "000000"
    })
    assert res_bad_otp.status_code == 400
    assert "invalid or expired" in res_bad_otp.json()["detail"].lower()

    # Submit with valid OTP generated for original email
    valid_otp = db.create_otp_challenge("old_email@example.com", purpose="email_change", ttl_seconds=300, user_id=user_id)

    res_good = c.post("/api/profile", json={
        "first_name": "Updated",
        "last_name": "User",
        "email": "new_email@example.com",
        "otp_code": valid_otp
    })
    assert res_good.status_code == 200
    profile_data = res_good.json()["profile"]
    assert profile_data["email"] == "new_email@example.com"
    assert profile_data["first_name"] == "Updated"
