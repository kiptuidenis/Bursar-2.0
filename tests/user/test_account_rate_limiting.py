import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_db, get_current_user_id
from app.core import config
from app.db.manager import DatabaseManager
from app.core.limiter import get_account_or_ip_key
from app.core.csrf import generate_csrf_token

DB_FILE = "test_account_rl.db"

@pytest.fixture
def client_and_db():
    import gc
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass
    db = DatabaseManager(DB_FILE)
    db.initialize()
    
    user_id = db.create_user("254711998877", "TestPassword123!")
    
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    
    client = TestClient(app)
    
    yield client, db, user_id
    
    app.dependency_overrides.clear()
    db.close()
    gc.collect()
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except PermissionError:
            pass

@pytest.fixture
def enable_limiter(monkeypatch):
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", True)
        try:
            app.state.limiter.reset()
        except Exception:
            pass
    yield
    monkeypatch.setattr(config, "IS_TEST_MODE", True)
    if hasattr(app.state, "limiter"):
        monkeypatch.setattr(app.state.limiter, "enabled", False)

def test_account_rate_limiting_spans_multiple_ips(client_and_db, enable_limiter):
    """
    Verify rate limiting tracks per-account/session identity (SEC-007), so rotating client IP headers
    does NOT bypass account rate limits for authenticated endpoints (e.g. /api/profile/deactivate with 3/minute limit).
    """
    client, db, user_id = client_and_db
    
    session_token = "test_session_token_123"
    csrf_token = generate_csrf_token()
    client.cookies.set("session_token", session_token)
    client.cookies.set("csrf_token", csrf_token)
    
    headers_ip1 = {"X-Forwarded-For": "10.0.0.1", "X-CSRF-Token": csrf_token}
    headers_ip2 = {"X-Forwarded-For": "10.0.0.2", "X-CSRF-Token": csrf_token}
    
    # 3 requests allowed per minute on profile deactivation
    res1 = client.post("/api/profile/deactivate", json={"password": "WrongPassword", "confirmation": "DELETE", "otp_code": "123456"}, headers=headers_ip1)
    assert res1.status_code == 401 # password wrong, but passed auth/csrf/rate-limit check
    
    res2 = client.post("/api/profile/deactivate", json={"password": "WrongPassword", "confirmation": "DELETE", "otp_code": "123456"}, headers=headers_ip1)
    res3 = client.post("/api/profile/deactivate", json={"password": "WrongPassword", "confirmation": "DELETE", "otp_code": "123456"}, headers=headers_ip2) # Switch IP!
    
    # 4th attempt from IP 2 (rotating IP) should STILL be blocked with 429 Too Many Requests because key is bound to session/user
    res4 = client.post("/api/profile/deactivate", json={"password": "WrongPassword", "confirmation": "DELETE", "otp_code": "123456"}, headers=headers_ip2)
    
    assert res4.status_code == 429, "Rotating IP MUST NOT bypass account-level rate limits"
