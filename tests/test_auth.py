import time
import pytest
from auth import SessionManager

@pytest.fixture
def manager():
    # Setup with a fixed secret for testing determinism
    return SessionManager(secret_key="test_signing_secret_key_123")

def test_generate_and_validate_session(manager):
    user_id = 42
    token = manager.create_session(user_id, expires_in_seconds=10)
    assert token is not None
    assert isinstance(token, str)
    
    # Validate token
    validated_id = manager.validate_session(token)
    assert validated_id == user_id

def test_session_expiration(manager):
    user_id = 100
    # Create session that expires immediately (0 seconds)
    token = manager.create_session(user_id, expires_in_seconds=0)
    
    # It should fail validation
    assert manager.validate_session(token) is None

def test_session_tampering(manager):
    user_id = 42
    token = manager.create_session(user_id, expires_in_seconds=10)
    
    # Try modifying user_id inside token (payload is structured as user_id:expiration:signature)
    parts = token.split(":")
    assert len(parts) == 3
    
    # Change user_id from 42 to 43
    parts[0] = "43"
    tampered_token = ":".join(parts)
    
    # Validation should fail due to signature mismatch
    assert manager.validate_session(tampered_token) is None
    
    # Try changing signature to something else
    parts = token.split(":")
    parts[2] = "abcdef0123456789"
    tampered_sig = ":".join(parts)
    assert manager.validate_session(tampered_sig) is None

def test_invalid_format(manager):
    assert manager.validate_session("invalidtoken") is None
    assert manager.validate_session("") is None
    assert manager.validate_session("123:456") is None

def test_different_secret_key():
    m1 = SessionManager(secret_key="secret_one")
    m2 = SessionManager(secret_key="secret_two")
    
    token = m1.create_session(5, expires_in_seconds=10)
    # Validation by m2 must fail because secret keys don't match
    assert m2.validate_session(token) is None
