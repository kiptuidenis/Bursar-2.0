import pytest
from unittest.mock import patch, MagicMock
from app.core import config
from app.services.recaptcha import verify_recaptcha_token

def test_verify_recaptcha_disabled(monkeypatch):
    monkeypatch.setattr(config, "RECAPTCHA_ENABLED", False)
    assert verify_recaptcha_token("fake_token") is True

def test_verify_recaptcha_missing_secret_or_token(monkeypatch):
    monkeypatch.setattr(config, "RECAPTCHA_ENABLED", True)
    monkeypatch.setattr(config, "RECAPTCHA_SECRET_KEY", "")
    # Missing secret key should log warning and return True for dev convenience
    assert verify_recaptcha_token("fake_token") is True

    monkeypatch.setattr(config, "RECAPTCHA_SECRET_KEY", "real_secret_key")
    # Missing token should return False
    assert verify_recaptcha_token(None) is False
    assert verify_recaptcha_token("") is False

@patch("httpx.post")
def test_verify_recaptcha_success(mock_post, monkeypatch):
    monkeypatch.setattr(config, "RECAPTCHA_ENABLED", True)
    monkeypatch.setattr(config, "RECAPTCHA_SECRET_KEY", "test_secret")
    monkeypatch.setattr(config, "RECAPTCHA_SCORE_THRESHOLD", 0.5)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "score": 0.9}
    mock_post.return_value = mock_resp

    result = verify_recaptcha_token("valid_token", client_ip="127.0.0.1")
    assert result is True
    mock_post.assert_called_once()

@patch("httpx.post")
def test_verify_recaptcha_low_score(mock_post, monkeypatch):
    monkeypatch.setattr(config, "RECAPTCHA_ENABLED", True)
    monkeypatch.setattr(config, "RECAPTCHA_SECRET_KEY", "test_secret")
    monkeypatch.setattr(config, "RECAPTCHA_SCORE_THRESHOLD", 0.5)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "score": 0.2}
    mock_post.return_value = mock_resp

    result = verify_recaptcha_token("bot_token")
    assert result is False

@patch("httpx.post")
def test_verify_recaptcha_failed(mock_post, monkeypatch):
    monkeypatch.setattr(config, "RECAPTCHA_ENABLED", True)
    monkeypatch.setattr(config, "RECAPTCHA_SECRET_KEY", "test_secret")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": False, "error-codes": ["invalid-input-response"]}
    mock_post.return_value = mock_resp

    result = verify_recaptcha_token("invalid_token")
    assert result is False

def test_auth_endpoints_with_recaptcha_enabled(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(config, "RECAPTCHA_ENABLED", True)
    monkeypatch.setattr(config, "RECAPTCHA_SECRET_KEY", "test_secret")

    client = TestClient(app)
    # Submission without token should be blocked with status code 400
    res = client.post("/api/auth/signup", json={"phone_number": "254799999999", "password": "password123"})
    assert res.status_code == 400
    assert "reCAPTCHA verification failed" in res.json()["detail"]

