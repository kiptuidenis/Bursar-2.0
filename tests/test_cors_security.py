import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import parse_allowed_origins


def test_parse_allowed_origins_valid():
    """Test valid origin strings are parsed, stripped of whitespace/trailing slashes, and returned."""
    raw = "  https://bursar.co.ke/ , http://localhost:8000  , https://app.bursar.co.ke:8443 "
    parsed = parse_allowed_origins(raw, is_test_mode=True, is_dev_mode=False)
    assert len(parsed) == 3
    assert "https://bursar.co.ke" in parsed
    assert "http://localhost:8000" in parsed
    assert "https://app.bursar.co.ke:8443" in parsed


def test_parse_allowed_origins_malformed_raises_error():
    """Test malformed origins (missing scheme, path segments) raise ValueError."""
    malformed_origins = [
        "bursar.co.ke",  # missing https://
        "https://bursar.co.ke/path/to/page",  # path segment not allowed in origin
        "ftp://bursar.co.ke",  # non-http(s) scheme
        "://bursar.co.ke",
    ]
    for bad_origin in malformed_origins:
        with pytest.raises(ValueError):
            parse_allowed_origins(bad_origin, is_test_mode=False, is_dev_mode=False)


def test_parse_allowed_origins_wildcard_rejection():
    """Test wildcard '*' is rejected when credentials are enabled."""
    with pytest.raises(ValueError) as exc_info:
        parse_allowed_origins("*", is_test_mode=False, is_dev_mode=False)
    assert "Wildcard '*' origin is forbidden" in str(exc_info.value)


def test_parse_allowed_origins_production_missing_raises_error():
    """Test missing ALLOWED_ORIGINS in production mode raises RuntimeError."""
    with pytest.raises(RuntimeError) as exc_info:
        parse_allowed_origins("", is_test_mode=False, is_dev_mode=False)
    assert "ALLOWED_ORIGINS environment variable must be explicitly defined in production" in str(exc_info.value)


def test_cors_authorized_origin_preflight():
    """Test OPTIONS preflight from authorized origin returns correct CORS headers."""
    client = TestClient(app)
    response = client.options(
        "/api/auth/me",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type, X-Background-Poll",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert response.headers.get("access-control-max-age") == "600"


def test_cors_unauthorized_origin_preflight_rejected():
    """Test OPTIONS preflight from unauthorized origin does not return allow-origin header."""
    client = TestClient(app)
    response = client.options(
        "/api/auth/me",
        headers={
            "Origin": "https://malicious-attacker.com",
            "Access-Control-Request-Method": "GET",
        }
    )
    # CORSMiddleware omits access-control-allow-origin header for untrusted origins
    assert response.headers.get("access-control-allow-origin") != "https://malicious-attacker.com"


def test_cors_credentialed_get_request():
    """Test GET request with credentials from authorized origin returns correct CORS response header."""
    client = TestClient(app)
    response = client.get(
        "/api/auth/config",
        headers={"Origin": "http://localhost:8000"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert response.headers.get("access-control-allow-credentials") == "true"
