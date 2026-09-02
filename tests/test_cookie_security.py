import pytest
import os
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.core.config import SESSION_COOKIE_SECURE

DB_FILE = "test_cookie_sec.db"

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
    
    user_id = db.create_user("254712345678", "TestPassword123!")
    
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

def test_logout_cookie_deletion_attributes(client_and_db):
    """Verify /api/auth/logout deletes both session_token and csrf_token cookies with explicit path=/ and security flags (SEC-006)."""
    client, db, user_id = client_and_db
    
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    
    # Check set-cookie headers returned by logout
    set_cookie_headers = res.headers.get_list("set-cookie") if hasattr(res.headers, "get_list") else res.raw_headers
    
    # Fastapi TestClient / HTTPX cookie check
    session_cookie_header = next((h for h in res.headers.raw if b"session_token=" in h[1]), None)
    csrf_cookie_header = next((h for h in res.headers.raw if b"csrf_token=" in h[1]), None)
    
    assert session_cookie_header is not None, "session_token deletion cookie MUST be returned on logout"
    assert csrf_cookie_header is not None, "csrf_token deletion cookie MUST be returned on logout"
    
    session_str = session_cookie_header[1].decode("utf-8").lower()
    csrf_str = csrf_cookie_header[1].decode("utf-8").lower()
    
    assert "path=/" in session_str, "session_token deletion cookie MUST specify path=/"
    assert "httponly" in session_str, "session_token deletion cookie MUST specify httponly"
    assert "path=/" in csrf_str, "csrf_token deletion cookie MUST specify path=/"

def test_deactivate_cookie_deletion_attributes(client_and_db):
    """Verify /api/profile/deactivate deletes session_token and csrf_token cookies with path=/ (SEC-006)."""
    client, db, user_id = client_and_db
    from app.db.models import User
    user = db.session.query(User).filter(User.id == user_id).first()
    otp_code = db.create_otp_challenge(user.email, purpose="account_deactivation", ttl_seconds=300, user_id=user_id)
    
    res = client.post("/api/profile/deactivate", json={"password": "TestPassword123!", "confirmation": "DELETE", "otp_code": otp_code})
    assert res.status_code == 200
    
    session_cookie_header = next((h for h in res.headers.raw if b"session_token=" in h[1]), None)
    csrf_cookie_header = next((h for h in res.headers.raw if b"csrf_token=" in h[1]), None)
    
    assert session_cookie_header is not None, "session_token deletion cookie MUST be returned on deactivate"
    assert csrf_cookie_header is not None, "csrf_token deletion cookie MUST be returned on deactivate"
    
    session_str = session_cookie_header[1].decode("utf-8").lower()
    csrf_str = csrf_cookie_header[1].decode("utf-8").lower()
    
    assert "path=/" in session_str, "session_token deletion cookie on deactivate MUST specify path=/"
    assert "path=/" in csrf_str, "csrf_token deletion cookie on deactivate MUST specify path=/"

def test_profile_logger_is_defined():
    """Verify profile.py defines logger so avatar cleanup error logging does not trigger NameError (SEC-017)."""
    from app.api.routers import profile
    assert hasattr(profile, "logger"), "profile.py MUST define a logger instance to prevent NameError on avatar cleanup failure"
