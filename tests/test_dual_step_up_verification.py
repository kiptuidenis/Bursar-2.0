import os
import pytest
import datetime
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession, OtpCode
from app.services.email import last_sent_otp_emails

DB_FILE = "test_dual_stepup.db"
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

def setup_authenticated_client(email="stepup@bursar.co.ke", password="Str0ng!P@ssw0rd"):
    client = TestClient(app)
    client.post("/api/auth/signup", json={"email": email, "password": password})
    otp_signup = last_sent_otp_emails[email]["otp_code"]
    client.post("/api/auth/verify-otp", json={"email": email, "otp_code": otp_signup, "purpose": "signup_2fa"})
    return client, email, password

def test_request_stepup_otp_dispatches_email():
    """Requesting step-up authorization OTP dispatches 6-digit email to authenticated user."""
    client, email, password = setup_authenticated_client("reqstepup@bursar.co.ke")
    
    res = client.post("/api/profile/request-stepup-otp", json={"purpose": "phone_update"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    assert email in last_sent_otp_emails
    otp_code = last_sent_otp_emails[email]["otp_code"]
    assert len(otp_code) == 6

def test_update_payout_phone_requires_password_and_otp():
    """Updating payout Safaricom phone number succeeds when valid password & OTP are provided."""
    client, email, password = setup_authenticated_client("payoutphone@bursar.co.ke")
    
    # Request step-up OTP
    client.post("/api/profile/request-stepup-otp", json={"purpose": "phone_update"})
    otp_code = last_sent_otp_emails[email]["otp_code"]

    # Submit payout phone update with Dual Step-Up Verification
    res = client.post("/api/profile/payout-phone", json={
        "payout_phone_number": "254712345678",
        "password": password,
        "otp_code": otp_code
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["payout_phone_number"] == "254712345678"

    # Verify profile reflects saved payout phone number
    res_prof = client.get("/api/profile")
    assert res_prof.json()["payout_phone_number"] == "254712345678"

def test_update_payout_phone_with_wrong_password_returns_401():
    """Updating payout phone with incorrect password fails with 401 Unauthorized."""
    client, email, password = setup_authenticated_client("wrongpwd@bursar.co.ke")
    
    client.post("/api/profile/request-stepup-otp", json={"purpose": "phone_update"})
    otp_code = last_sent_otp_emails[email]["otp_code"]

    res = client.post("/api/profile/payout-phone", json={
        "payout_phone_number": "254712345678",
        "password": "WrongPassword123!",
        "otp_code": otp_code
    })
    assert res.status_code == 401
    assert "Invalid password credential." in res.json()["detail"]

def test_update_payout_phone_with_wrong_otp_returns_400():
    """Updating payout phone with incorrect OTP fails with 400 Bad Request."""
    client, email, password = setup_authenticated_client("wrongotp@bursar.co.ke")

    res = client.post("/api/profile/payout-phone", json={
        "payout_phone_number": "254712345678",
        "password": password,
        "otp_code": "000000"
    })
    assert res.status_code == 400
    assert "Invalid or expired verification code." in res.json()["detail"]

def test_budget_lock_with_stepup_otp_and_payout_phone():
    """Locking budget with mandatory payout phone number enforces dual step-up verification."""
    client, email, password = setup_authenticated_client("budgetlock@bursar.co.ke")
    
    # 1. Deposit funds
    db = get_test_db()
    user = db.get_user_by_email(email)
    db.adjust_balance(user.id, 5000)
    
    # 2. Add budget item
    client.post("/api/budget/items", json={"category": "Food", "amount": 500})
    
    # 3. Request step-up OTP for budget lock
    client.post("/api/profile/request-stepup-otp", json={"purpose": "payout_stepup"})
    otp_code = last_sent_otp_emails[email]["otp_code"]

    eat_tz = datetime.timezone(datetime.timedelta(hours=3))
    today_dt = datetime.datetime.now(eat_tz)
    start_str = (today_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    end_str = (today_dt + datetime.timedelta(days=15)).strftime("%Y-%m-%d")

    # 4. Lock budget with Dual Step-Up Verification
    res_lock = client.post("/api/budget/lock", json={
        "start_date": start_str,
        "end_date": end_str,
        "payout_phone_number": "254799112233",
        "password": password,
        "otp_code": otp_code
    })
    assert res_lock.status_code == 200
    assert res_lock.json()["status"] == "success"

    # Verify payout phone saved to profile
    res_prof = client.get("/api/profile")
    assert res_prof.json()["payout_phone_number"] == "254799112233"
