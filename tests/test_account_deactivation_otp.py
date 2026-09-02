import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Session as DbSession, OtpCode, Wallet
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_account_deactivation_otp.db"
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

def _create_authenticated_client(email="deactivate_user@example.com", password="Str0ng!P@ssw0rd"):
    db = get_test_db()
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email, pwd_hash, salt)
    
    c = TestClient(app)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id, email

def test_request_deactivation_otp_dispatches_code_to_user_email():
    """Verify that requesting deactivation OTP generates challenge on user's registered email."""
    c, user_id, email = _create_authenticated_client("deact_otp@example.com")
    db = get_test_db()

    res = c.post("/api/profile/request-stepup-otp", json={"purpose": "account_deactivation"})
    assert res.status_code == 200
    assert "authorization code sent" in res.json()["message"].lower()

    otp_rec = db.get_otp_record(email, "account_deactivation")
    assert otp_rec is not None
    assert otp_rec.user_id == user_id

def test_deactivate_missing_or_invalid_otp_fails():
    """Verify that deactivation requires a valid 6-digit OTP code."""
    c, user_id, email = _create_authenticated_client("deact_fail@example.com")
    db = get_test_db()

    # 1. Missing OTP code
    res_no_otp = c.post("/api/profile/deactivate", json={
        "password": "Str0ng!P@ssw0rd",
        "confirmation": "DELETE"
    })
    assert res_no_otp.status_code == 422  # Pydantic validation error for missing field

    # 2. Invalid/wrong OTP code
    res_bad_otp = c.post("/api/profile/deactivate", json={
        "password": "Str0ng!P@ssw0rd",
        "confirmation": "DELETE",
        "otp_code": "000000"
    })
    assert res_bad_otp.status_code == 400
    assert "invalid or expired" in res_bad_otp.json()["detail"].lower()

def test_deactivate_dual_factor_password_and_otp_success():
    """Verify that valid password, confirmation phrase, and valid OTP code deactivates account."""
    c, user_id, email = _create_authenticated_client("deact_success@example.com", "Str0ng!P@ssw0rd")
    db = get_test_db()

    # Generate valid OTP challenge
    valid_otp = db.create_otp_challenge(email, purpose="account_deactivation", ttl_seconds=300, user_id=user_id)

    # 1. Mismatched confirmation phrase fails even with valid OTP
    res_bad_phrase = c.post("/api/profile/deactivate", json={
        "password": "Str0ng!P@ssw0rd",
        "confirmation": "WRONG",
        "otp_code": valid_otp
    })
    assert res_bad_phrase.status_code == 400

    # 2. Incorrect password fails even with valid OTP
    res_bad_pwd = c.post("/api/profile/deactivate", json={
        "password": "WrongPassword!123",
        "confirmation": "DELETE",
        "otp_code": valid_otp
    })
    assert res_bad_pwd.status_code == 401

    # 3. Successful deactivation with correct password, phrase, and OTP
    res_success = c.post("/api/profile/deactivate", json={
        "password": "Str0ng!P@ssw0rd",
        "confirmation": "DELETE",
        "otp_code": valid_otp
    })
    assert res_success.status_code == 200

    # Verify user record is completely removed from DB
    user = db.session.query(User).filter(User.id == user_id).first()
    assert user is None

    # Subsequent API requests with session are rejected with 401
    assert c.get("/api/profile").status_code == 401
