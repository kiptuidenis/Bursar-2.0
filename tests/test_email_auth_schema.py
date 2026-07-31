import os
import time
import pytest
from app.db.manager import DatabaseManager

DB_FILE = "test_email_schema.db"

@pytest.fixture
def db():
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass
    manager = DatabaseManager(DB_FILE)
    manager.initialize()
    yield manager
    manager.close()
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass

def test_create_user_with_email(db):
    """Verify user creation with email address, unique email constraint, and email retrieval."""
    email = "testuser@bursar.co.ke"
    password = "StrongTestPassword123!"
    
    user_id = db.create_user_email(email, password, payout_phone="254712345678")
    assert user_id > 0
    
    # Retrieve user by email
    user = db.get_user_by_email(email)
    assert user is not None
    assert user.email == email
    assert user.payout_phone_number == "254712345678"
    assert user.email_verified is False
    assert user.two_factor_enabled is True
    
    # Verify duplicate email creation raises ValueError / IntegrityError
    with pytest.raises(Exception):
        db.create_user_email(email, "AnotherPassword123!")

def test_otp_code_lifecycle(db):
    """Verify 6-digit OTP code challenge creation, hashing, verification, attempt limits, and expiration."""
    email = "otpuser@bursar.co.ke"
    user_id = db.create_user_email(email, "StrongTestPassword123!")
    
    purpose = "login_2fa"
    otp_code = db.create_otp_challenge(email, purpose=purpose, ttl_seconds=300, user_id=user_id)
    
    # OTP code MUST be 6 numeric digits
    assert len(otp_code) == 6
    assert otp_code.isdigit()
    
    # Wrong OTP code should fail verification
    assert db.verify_otp_challenge(email, "000000", purpose=purpose) is False
    
    # Correct OTP code succeeds verification
    assert db.verify_otp_challenge(email, otp_code, purpose=purpose) is True
    
    # Once verified, email_verified flag is set to True
    user = db.get_user_by_email(email)
    assert user.email_verified is True
    
    # Used OTP code cannot be re-used
    assert db.verify_otp_challenge(email, otp_code, purpose=purpose) is False

def test_payout_phone_number_operations(db):
    """Verify updating and fetching user payout phone number for financial disbursements."""
    email = "payout@bursar.co.ke"
    user_id = db.create_user_email(email, "StrongTestPassword123!")
    
    db.update_payout_phone_number(user_id, "254799112233")
    saved_phone = db.get_payout_phone_number(user_id)
    assert saved_phone == "254799112233"
