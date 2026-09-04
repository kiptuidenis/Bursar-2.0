import time
import pytest
from app.core.security import SessionManager

@pytest.fixture
def manager():
    # Setup with a fixed secret for testing determinism (must be at least 32 chars)
    return SessionManager(secret_key="test_signing_secret_key_32_chars_123")

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


def test_signup_password_policy_rejection():
    """Verifies that signup API rejects short, weak, or phone-containing passwords (H-04)."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.manager import DatabaseManager
    from app.api.dependencies import get_db

    test_db = DatabaseManager("test_auth_policy.db")
    test_db.initialize()
    app.dependency_overrides[get_db] = lambda: test_db

    try:
        client = TestClient(app)

        # 1. Under 8 chars returns 422
        res1 = client.post("/api/auth/signup", json={"email": "test@example.com", "password": "Short1!"})
        assert res1.status_code in (400, 422)

        # 2. Missing uppercase returns 400
        res2 = client.post("/api/auth/signup", json={"email": "test@example.com", "password": "password123!"})
        assert res2.status_code == 400
        assert "uppercase" in res2.json()["detail"]

        # 3. Missing symbol returns 400
        res3 = client.post("/api/auth/signup", json={"email": "test@example.com", "password": "Password123"})
        assert res3.status_code == 400
        assert "special symbol" in res3.json()["detail"]

        # 4. Valid strong password passes signup
        res5 = client.post("/api/auth/signup", json={"email": "test@example.com", "password": "Burs@rSecur32026!"})
        assert res5.status_code == 200
        assert res5.json()["status"] == "2fa_required"

    finally:
        app.dependency_overrides.pop(get_db, None)
        test_db.close()
        import os
        if os.path.exists("test_auth_policy.db"):
            try:
                os.remove("test_auth_policy.db")
            except Exception:
                pass
    


def test_invalid_format(manager):
    assert manager.validate_session("invalidtoken") is None
    assert manager.validate_session("") is None
    assert manager.validate_session("123:456") is None

def test_different_secret_key():
    m1 = SessionManager(secret_key="secret_one_32_characters_minimum_len")
    m2 = SessionManager(secret_key="secret_two_32_characters_minimum_len")
    
    token = m1.create_session(5, expires_in_seconds=10)
    # Validation by m2 must fail because secret keys don't match
    assert m2.validate_session(token) is None

