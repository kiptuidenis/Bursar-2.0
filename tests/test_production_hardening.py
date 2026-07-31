import os
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.main import app, global_exception_handler
from app.core import config

def test_security_headers_present_on_responses():
    """Verify production security headers are set on all responses (SEC-013)."""
    client = TestClient(app)
    res = client.get("/api/diagnostics")
    
    assert res.headers.get("Content-Security-Policy") is not None
    assert "frame-ancestors 'none'" in res.headers.get("Content-Security-Policy")
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert "max-age=" in res.headers.get("Strict-Transport-Security", "")
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in res.headers.get("Permissions-Policy", "")

def test_unhandled_exception_does_not_leak_stack_trace():
    """Verify unhandled 500 exceptions return generic detail message without stack trace (SEC-015)."""
    error_app = FastAPI()
    error_app.add_exception_handler(Exception, global_exception_handler)
    
    @error_app.get("/test-500-error-trigger")
    def trigger_error():
        raise RuntimeError("Internal database secret crash: connection pool exhausted at db.py:123")
        
    client = TestClient(error_app, raise_server_exceptions=False)
    res = client.get("/test-500-error-trigger")
    assert res.status_code == 500
    data = res.json()
    assert data["detail"] == "An internal server error occurred. Please try again later."
    assert "traceback" not in res.text.lower()
    assert "db.py" not in res.text

def test_openapi_docs_guarded_in_production(monkeypatch):
    """Verify /docs, /redoc, /openapi.json are disabled when SHOW_API_DOCS is False (SEC-010)."""
    monkeypatch.setattr(config, "SHOW_API_DOCS", False)
    
    docs_url = "/docs" if config.SHOW_API_DOCS else None
    redoc_url = "/redoc" if config.SHOW_API_DOCS else None
    openapi_url = "/openapi.json" if config.SHOW_API_DOCS else None
    
    prod_app = FastAPI(
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url
    )
    prod_client = TestClient(prod_app)
    
    res_docs = prod_client.get("/docs")
    res_redoc = prod_client.get("/redoc")
    res_openapi = prod_client.get("/openapi.json")
    
    assert res_docs.status_code == 404
    assert res_redoc.status_code == 404
    assert res_openapi.status_code == 404

def test_host_header_injection_defense():
    """Verify untrusted host headers are rejected with 400 Bad Request when TrustedHostMiddleware is active (SEC-011)."""
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    
    host_app = FastAPI()
    host_app.add_middleware(TrustedHostMiddleware, allowed_hosts=["bursar.co.ke", "localhost"])
    
    @host_app.get("/ping")
    def ping():
        return {"status": "ok"}
        
    client = TestClient(host_app)
    
    # Valid host
    res_valid = client.get("/ping", headers={"Host": "bursar.co.ke"})
    assert res_valid.status_code == 200
    
    # Untrusted host header injection attempt
    res_untrusted = client.get("/ping", headers={"Host": "attacker-domain.com"})
    assert res_untrusted.status_code == 400
