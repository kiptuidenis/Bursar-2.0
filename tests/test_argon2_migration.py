import pytest
from app.db.manager import DatabaseManager

def test_new_user_password_hashed_with_argon2id():
    """Verify newly registered users have passwords hashed with Argon2id."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    
    user_id = db.create_user("254711111111", "StrongPass123!")
    profile = db.get_profile(user_id)
    
    assert profile["password_hash"].startswith("$argon2id$"), "New password hash MUST use Argon2id scheme ($argon2id$...)"
    assert profile["salt"] == "argon2", "Salt indicator for Argon2id should be 'argon2'"
    db.close()

def test_argon2id_password_verification():
    """Verify password authentication succeeds with Argon2id hash."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    
    user_id = db.create_user("254722222222", "StrongPass123!")
    auth_user_id = db.authenticate_user("254722222222", "StrongPass123!")
    
    assert auth_user_id == user_id
    assert db.authenticate_user("254722222222", "WrongPassword123!") is None
    db.close()

def test_legacy_pbkdf2_transparent_migration_on_login():
    """
    Verify legacy PBKDF2 user can log in AND their stored hash is transparently
    upgraded to Argon2id upon successful authentication.
    """
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    
    password = "LegacyPassword123!"
    # Manually create a user with legacy PBKDF2 hash
    pbkdf2_hash, pbkdf2_salt = db._hash_password_pbkdf2_legacy(password)
    
    from app.db.models import User, Settings
    legacy_user = User(
        phone_number="254733333333",
        password_hash=pbkdf2_hash,
        salt=pbkdf2_salt
    )
    db.session.add(legacy_user)
    db._commit()
    db.session.add(Settings(user_id=legacy_user.id, phone_number="254733333333"))
    db._commit()
    
    # 1. Verify user can authenticate with legacy hash
    auth_id = db.authenticate_user("254733333333", password)
    assert auth_id == legacy_user.id
    
    # 2. Check that stored hash was automatically re-hashed to Argon2id in DB!
    upgraded_profile = db.get_profile(legacy_user.id)
    assert upgraded_profile["password_hash"].startswith("$argon2id$"), "Legacy PBKDF2 hash MUST be transparently upgraded to Argon2id on login!"
    assert upgraded_profile["salt"] == "argon2"
    
    # 3. Verify user can still authenticate after upgrade
    assert db.authenticate_user("254733333333", password) == legacy_user.id
    db.close()
