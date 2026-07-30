import pytest
import hmac
from unittest.mock import patch
from app.db.manager import DatabaseManager

def test_constant_time_password_verification_success():
    """Verify correct password succeeds using constant-time comparison."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    
    password = "TestPassword123!"
    hash_hex, salt_hex = db._hash_password(password)
    
    assert db._verify_password(password, hash_hex, salt_hex) is True
    db.close()

def test_constant_time_password_verification_failure():
    """Verify incorrect password fails safely."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    
    password = "TestPassword123!"
    hash_hex, salt_hex = db._hash_password(password)
    
    assert db._verify_password("WrongPassword123!", hash_hex, salt_hex) is False
    db.close()

def test_compare_digest_is_invoked():
    """Verify hmac.compare_digest is explicitly called during password verification to eliminate timing side-channels."""
    db = DatabaseManager("sqlite:///:memory:")
    db.initialize()
    
    password = "TestPassword123!"
    hash_hex, salt_hex = db._hash_password(password)
    
    with patch("hmac.compare_digest", wraps=hmac.compare_digest) as mock_compare:
        result = db._verify_password(password, hash_hex, salt_hex)
        assert result is True
        assert mock_compare.called, "hmac.compare_digest MUST be called during password verification for constant-time safety!"
        
    db.close()
