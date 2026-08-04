import os
import pytest
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, OtpCode

DB_FILE = "test_email_schema.db"

@pytest.fixture
def db():
    import gc
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass
    manager = DatabaseManager(DB_FILE)
    manager.initialize()
    yield manager
    manager.close()
    gc.collect()
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass

def test_user_creation_with_normalized_lowercase_email(db):
    """Verify create_user_email normalizes emails to lowercase and enforces uniqueness (Subphase 2.1)."""
    user_id = db.create_user_email("Test.User@Bursar.Co.Ke", "Str0ng!P@ssw0rd")
    assert user_id > 0
    
    # Verify email stored as lowercase
    user = db.session.query(User).filter(User.id == user_id).first()
    assert user is not None
    assert user.email == "test.user@bursar.co.ke"
    assert user.payout_phone_number == ""
    assert user.email_verified is False
    assert user.two_factor_enabled is True
    
    # Case-insensitive query lookup
    fetched = db.get_user_by_email("TEST.USER@BURSAR.CO.KE")
    assert fetched is not None
    assert fetched.id == user_id
    
    # Duplicate registration attempt raises ValueError
    with pytest.raises(ValueError) as exc_info:
        db.create_user_email("test.user@bursar.co.ke", "AnotherPass123!")
    assert "already exists" in str(exc_info.value).lower()

def test_update_and_get_payout_phone_number(db):
    """Verify payout_phone_number operations on User model (Subphase 2.1)."""
    user_id = db.create_user_email("payout.test@bursar.co.ke", "Str0ng!P@ssw0rd")
    assert db.get_payout_phone_number(user_id) == ""
    
    # Update payout phone number
    db.update_payout_phone_number(user_id, "254799887766")
    assert db.get_payout_phone_number(user_id) == "254799887766"
    
    user = db.session.query(User).filter(User.id == user_id).first()
    assert user.payout_phone_number == "254799887766"

def test_otp_challenge_creation_and_hash_storage(db):
    """Verify create_otp_challenge stores hashed OTP codes and invalidates prior codes (Subphase 2.1)."""
    email = "otp.test@bursar.co.ke"
    user_id = db.create_user_email(email, "Str0ng!P@ssw0rd")
    
    raw_otp1 = db.create_otp_challenge(email, purpose="2fa_login", user_id=user_id)
    assert len(raw_otp1) == 6
    assert raw_otp1.isdigit()
    
    otp_record1 = db.session.query(OtpCode).filter(OtpCode.email == email, OtpCode.purpose == "2fa_login").first()
    assert otp_record1 is not None
    assert otp_record1.otp_code_hash.startswith("$argon2id$")
    
    # Creating second challenge invalidates the first
    raw_otp2 = db.create_otp_challenge(email, purpose="2fa_login", user_id=user_id)
    assert len(raw_otp2) == 6
    assert raw_otp2 != raw_otp1
    
    records = db.session.query(OtpCode).filter(OtpCode.email == email, OtpCode.purpose == "2fa_login").all()
    assert len(records) == 1
