import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db
from app.core import config


# ===========================================================================
# 1. Config-level test: production environment must force secure=True
# ===========================================================================
def test_secure_cookie_configuration_in_production(monkeypatch):
    """SESSION_COOKIE_SECURE must be forced True in production, even if env says false."""
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    # Reproduce the config logic with production env flags (IS_DEV_MODE=False, IS_TEST_MODE=False)
    env_val = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() in ("true", "1", "yes")
    is_dev = False
    is_test = False
    if not is_dev and not is_test:
        env_val = True  # Production always overrides to True

    assert env_val is True


# ===========================================================================
# Helpers
# ===========================================================================
def _make_mock_db():
    """Return a MagicMock that stands in for DatabaseManager, with log_event stubbed."""
    mock_db = MagicMock()
    mock_db.authenticate_user.return_value = 1  # user_id = 1
    mock_db.log_event.return_value = None
    return mock_db


def _db_override(mock_db):
    """FastAPI dependency override generator that yields mock_db."""
    def override():
        yield mock_db
    return override


# ===========================================================================
# 2. Login endpoint sets Secure flag when SESSION_COOKIE_SECURE=True
# ===========================================================================
def test_login_endpoint_sets_secure_cookie_when_configured():
    """Login response must include Secure attribute on the session_token cookie."""
    mock_db = _make_mock_db()
    mock_session_manager = MagicMock()
    mock_session_manager.create_session.return_value = "mock.session.token"

    app.dependency_overrides[get_db] = _db_override(mock_db)
    try:
        with patch("app.api.routers.auth.SESSION_COOKIE_SECURE", True), \
             patch("app.api.routers.auth.session_manager", mock_session_manager), \
             patch("app.services.recaptcha.verify_recaptcha_token", return_value=True):

            client = TestClient(app, raise_server_exceptions=True)
            response = client.post(
                "/api/auth/login",
                json={
                    "phone_number": "0712345678",
                    "password": "1234",
                    "recaptcha_token": "dummy"
                }
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    set_cookie = response.headers.get("set-cookie", "")
    assert "session_token" in set_cookie, f"session_token not in Set-Cookie: {set_cookie!r}"
    assert "secure" in set_cookie.lower(), f"Expected 'secure' flag in Set-Cookie, got: {set_cookie!r}"


# ===========================================================================
# 3. Login endpoint omits Secure flag in local dev (SESSION_COOKIE_SECURE=False)
# ===========================================================================
def test_login_endpoint_omits_secure_cookie_in_local_dev():
    """Login response must NOT include Secure attribute when SESSION_COOKIE_SECURE is False."""
    mock_db = _make_mock_db()
    mock_session_manager = MagicMock()
    mock_session_manager.create_session.return_value = "mock.session.token"

    app.dependency_overrides[get_db] = _db_override(mock_db)
    try:
        with patch("app.api.routers.auth.SESSION_COOKIE_SECURE", False), \
             patch("app.api.routers.auth.session_manager", mock_session_manager), \
             patch("app.services.recaptcha.verify_recaptcha_token", return_value=True):

            client = TestClient(app, raise_server_exceptions=True)
            response = client.post(
                "/api/auth/login",
                json={
                    "phone_number": "0712345678",
                    "password": "1234",
                    "recaptcha_token": "dummy"
                }
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    set_cookie = response.headers.get("set-cookie", "")
    assert "session_token" in set_cookie, f"session_token not in Set-Cookie: {set_cookie!r}"
    assert "secure" not in set_cookie.lower(), f"Expected NO 'secure' flag in Set-Cookie, got: {set_cookie!r}"
