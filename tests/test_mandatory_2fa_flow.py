import os
import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession, OtpCode
from app.services.email import last_sent_otp_emails

DB_FILE = "test_mandatory_2fa_flow.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

@pytest.fixture(autouse=True)
def clean_db():
    global test_db_manager
    if test_db_manager:
        test_db_manager.close()
        test_db_manager = None
    for f in (DB_FILE, DB_FILE + "-shm", DB_FILE + "-wal"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
    app.dependency_overrides[get_db] = get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)
    if test_db_manager:
        test_db_manager.close()
        test_db_manager = None
    for f in (DB_FILE, DB_FILE + "-shm", DB_FILE + "-wal"):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

def test_signup_triggers_2fa_otp_without_issuing_cookie():
    """Signup requires email + password, dispatches 6-digit OTP email, and does NOT issue session token until verified."""
    client = TestClient(app)
    email = "newuser@bursar.co.ke"
    password = "Str0ng!P@ssw0rd"

    res = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "2fa_required"
    assert data["email"] == email
    assert data["purpose"] == "signup_2fa"
    
    # Crucial security check: Session cookie MUST NOT be set yet!
    assert "session_token" not in res.cookies

    # Verify mock email received
    assert email in last_sent_otp_emails
    otp_code = last_sent_otp_emails[email]["otp_code"]
    assert len(otp_code) == 6

def test_verify_otp_completes_signup_and_issues_session_cookie():
    """Verifying 6-digit signup OTP issues session token & CSRF cookies and marks email_verified=True."""
    client = TestClient(app)
    email = "verifyuser@bursar.co.ke"
    password = "Str0ng!P@ssw0rd"

    # Step 1: Signup
    client.post("/api/auth/signup", json={"email": email, "password": password})
    otp_code = last_sent_otp_emails[email]["otp_code"]

    # Step 2: Verify OTP
    res_verify = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp_code": otp_code,
        "purpose": "signup_2fa"
    })
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "success"
    
    # Session & CSRF cookies MUST be set
    assert "session_token" in res_verify.cookies
    assert "csrf_token" in res_verify.cookies

    # Verify profile request succeeds with authenticated session
    res_profile = client.get("/api/profile")
    assert res_profile.status_code == 200
    assert res_profile.json()["email"] == email

def test_login_requires_password_and_triggers_2fa_otp():
    """Login verifies password, dispatches fresh 6-digit OTP code, and requires OTP verification before session issuance."""
    client = TestClient(app)
    email = "login2fa@bursar.co.ke"
    password = "Str0ng!P@ssw0rd"

    # Signup & verify
    client.post("/api/auth/signup", json={"email": email, "password": password})
    otp_signup = last_sent_otp_emails[email]["otp_code"]
    client.post("/api/auth/verify-otp", json={"email": email, "otp_code": otp_signup, "purpose": "signup_2fa"})
    
    # Clear cookies (simulate logged out client)
    client.cookies.clear()

    # Step 1: Login with Email & Password
    res_login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res_login.status_code == 200
    assert res_login.json()["status"] == "2fa_required"
    assert "session_token" not in res_login.cookies

    # Fetch fresh login OTP
    otp_login = last_sent_otp_emails[email]["otp_code"]

    # Step 2: Verify Login OTP
    res_verify = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp_code": otp_login,
        "purpose": "login_2fa"
    })
    assert res_verify.status_code == 200
    assert "session_token" in res_verify.cookies

def test_login_with_invalid_password_returns_401():
    """Login with invalid password fails with 401 Unauthorized without dispatching OTP."""
    client = TestClient(app)
    email = "wrongpass@bursar.co.ke"
    client.post("/api/auth/signup", json={"email": email, "password": "Str0ng!P@ssw0rd"})
    last_sent_otp_emails.pop(email, None)

    res = client.post("/api/auth/login", json={"email": email, "password": "WrongPassword123!"})
    assert res.status_code == 401
    assert "Invalid email address or password." in res.json()["detail"]
    assert email not in last_sent_otp_emails

def test_verify_otp_with_invalid_code_returns_400():
    """Verifying invalid OTP code returns 400 Bad Request."""
    client = TestClient(app)
    email = "invalidotp@bursar.co.ke"
    client.post("/api/auth/signup", json={"email": email, "password": "Str0ng!P@ssw0rd"})

    res = client.post("/api/auth/verify-otp", json={
        "email": email,
        "otp_code": "000000",
        "purpose": "signup_2fa"
    })
    assert res.status_code == 400
    assert "Invalid or expired verification code." in res.json()["detail"]

def test_resend_otp_dispatches_new_code():
    """Resending OTP dispatches a fresh 6-digit OTP code."""
    client = TestClient(app)
    email = "resend@bursar.co.ke"
    client.post("/api/auth/signup", json={"email": email, "password": "Str0ng!P@ssw0rd"})
    first_otp = last_sent_otp_emails[email]["otp_code"]

    res_resend = client.post("/api/auth/resend-otp", json={"email": email, "purpose": "signup_2fa"})
    assert res_resend.status_code == 200
    assert res_resend.json()["status"] == "success"
    
    second_otp = last_sent_otp_emails[email]["otp_code"]
    assert len(second_otp) == 6
