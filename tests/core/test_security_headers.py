import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession

DB_FILE = "test_security_headers.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
    db = get_test_db()
    db.session.query(DbSession).delete()
    db.session.query(BudgetItem).delete()
    db.session.query(Log).delete()
    db.session.query(Deposit).delete()
    db.session.query(Payout).delete()
    db.session.query(Settings).delete()
    db.session.query(User).delete()
    db._commit()
    yield
    app.dependency_overrides.pop(get_db, None)
    db.close()

def test_security_headers_present_on_200_ok():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200

    headers = response.headers
    assert "Content-Security-Policy" in headers
    assert "X-Frame-Options" in headers
    assert headers["X-Frame-Options"] == "DENY"
    assert "X-Content-Type-Options" in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Strict-Transport-Security" in headers
    assert "max-age=31536000" in headers["Strict-Transport-Security"]
    assert "Referrer-Policy" in headers
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in headers
    assert "Cross-Origin-Opener-Policy" in headers
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "Cross-Origin-Resource-Policy" in headers
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"

def test_csp_directives_strictness():
    client = TestClient(app)
    response = client.get("/")
    csp = response.headers.get("Content-Security-Policy", "")

    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]  # No unsafe-inline in script-src
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp

def test_security_headers_present_on_error_responses():
    client = TestClient(app)
    
    # 404 Not Found response
    res_404 = client.get("/api/nonexistent-route-12345")
    assert res_404.status_code == 404
    assert "X-Content-Type-Options" in res_404.headers
    assert "Content-Security-Policy" in res_404.headers
    assert "X-Frame-Options" in res_404.headers

    # 422 Unprocessable Entity response (Pydantic validation error)
    res_422 = client.post("/api/auth/signup", json={"invalid": "payload"})
    assert res_422.status_code == 422
    assert "X-Content-Type-Options" in res_422.headers
    assert "Content-Security-Policy" in res_422.headers
