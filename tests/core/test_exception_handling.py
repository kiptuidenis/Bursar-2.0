import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager

def test_unhandled_exception_does_not_leak_raw_details(monkeypatch):
    """
    Simulate an unhandled internal exception during a real API call to verify 500 responses return a generic,
    sanitized error message instead of raw python exception strings or SQL tracebacks.
    """
    def mock_broken_auth(*args, **kwargs):
        raise RuntimeError("SQLAlchemy OperationalError 1054: Unknown column 'users.failed_login_attempts'")

    monkeypatch.setattr(DatabaseManager, "is_account_locked", mock_broken_auth)

    client = TestClient(app, raise_server_exceptions=False)
    res = client.post("/api/auth/login", json={"phone_number": "254712345678", "password": "1234password"})

    assert res.status_code == 500
    detail = res.json()["detail"]

    # Verify raw python exception text or SQL error strings are NEVER exposed to clients
    assert "SQLAlchemy" not in detail
    assert "Unknown column" not in detail
    assert "RuntimeError" not in detail
    assert detail == "An internal server error occurred. Please try again later."
