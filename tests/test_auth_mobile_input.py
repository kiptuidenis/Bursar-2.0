import re
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager

def test_index_html_auth_input_attributes():
    """Verify index.html has text type and inputmode for alphanumeric keyboard on mobile."""
    with open("src/app/static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    # Find the auth-phone input tag
    match = re.search(r'<input[^>]*id=["\']auth-phone["\'][^>]*>', html)
    assert match is not None, "Could not find input with id='auth-phone'"
    tag = match.group(0)

    assert 'type="text"' in tag
    assert 'inputmode="text"' in tag
    assert "user@example.com" in tag

def test_signup_rejects_phone_only_registration(tmp_path, monkeypatch):
    """Verify signup API strictly enforces email registration and rejects phone-only signups."""
    test_db_path = str(tmp_path / "test_auth_mobile.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("RECAPTCHA_ENABLED", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()
    db.close()

    with TestClient(app) as client:
        # 1. Phone-only signup attempt fails
        res_phone = client.post("/api/auth/signup", json={
            "phone_number": "254712345678",
            "password": "Secure!Key8899"
        })
        assert res_phone.status_code == 400
        assert "Registration using phone numbers is disabled" in res_phone.json()["detail"]

        # 2. Valid email signup returns 2fa_required
        res_email = client.post("/api/auth/signup", json={
            "email": "newuser@example.com",
            "password": "Secure!Key8899"
        })
        assert res_email.status_code == 200
        assert res_email.json()["status"] == "2fa_required"
