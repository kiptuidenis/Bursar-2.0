import os
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_auth.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")
    
    db = DatabaseManager(test_db_path)
    db.initialize()

    # Seed test administrators
    pwd_hash = hash_password_argon2("SuperAdmin!Pass2026")
    db.create_admin_user(
        email="superadmin@bursar.co.ke",
        password_hash=pwd_hash,
        salt="argon2",
        role="superadmin"
    )

    inactive_hash = hash_password_argon2("Inactive!Pass2026")
    admin_inactive_id = db.create_admin_user(
        email="disabled@bursar.co.ke",
        password_hash=inactive_hash,
        salt="argon2",
        role="support"
    )
    db.set_admin_active_status(admin_inactive_id, is_active=False)

    db.close()
    with TestClient(app) as test_client:
        yield test_client

def test_admin_login_success(client):
    """Admin login with valid credentials sets HTTP-only cookie and returns admin metadata."""
    res = client.post("/api/admin/auth/login", json={
        "email": "superadmin@bursar.co.ke",
        "password": "SuperAdmin!Pass2026"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["admin"]["email"] == "superadmin@bursar.co.ke"
    assert data["admin"]["role"] == "superadmin"
    assert "admin_session_token" in res.cookies

def test_admin_login_invalid_password(client):
    """Admin login with wrong password returns 401."""
    res = client.post("/api/admin/auth/login", json={
        "email": "superadmin@bursar.co.ke",
        "password": "WrongPassword123!"
    })
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]

def test_admin_login_nonexistent_email(client):
    """Nonexistent admin email returns generic 401 to prevent enumeration."""
    res = client.post("/api/admin/auth/login", json={
        "email": "nonexistent@bursar.co.ke",
        "password": "SuperAdmin!Pass2026"
    })
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]

def test_admin_account_lockout_after_5_failed_attempts(client):
    """Admin account is locked for 15 minutes after 5 consecutive failed attempts."""
    for i in range(4):
        res = client.post("/api/admin/auth/login", json={
            "email": "superadmin@bursar.co.ke",
            "password": f"WrongAttempt{i}"
        })
        assert res.status_code == 401

    # 5th failed attempt triggers lockout
    res_5 = client.post("/api/admin/auth/login", json={
        "email": "superadmin@bursar.co.ke",
        "password": "WrongAttempt5"
    })
    assert res_5.status_code == 403
    assert "locked" in res_5.json()["detail"].lower()

    # Subsequent attempt with CORRECT password is still locked
    res_locked = client.post("/api/admin/auth/login", json={
        "email": "superadmin@bursar.co.ke",
        "password": "SuperAdmin!Pass2026"
    })
    assert res_locked.status_code == 403
    assert "locked" in res_locked.json()["detail"].lower()

def test_admin_login_disabled_account(client):
    """Disabled admin account cannot log in."""
    res = client.post("/api/admin/auth/login", json={
        "email": "disabled@bursar.co.ke",
        "password": "Inactive!Pass2026"
    })
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"].lower()

def test_admin_auth_me_and_logout_flow(client):
    """Verify /me profile endpoint and logout session invalidation."""
    # 1. Login
    login_res = client.post("/api/admin/auth/login", json={
        "email": "superadmin@bursar.co.ke",
        "password": "SuperAdmin!Pass2026"
    })
    assert login_res.status_code == 200
    session_token = login_res.cookies.get("admin_session_token")
    assert session_token is not None

    # 2. Get current admin profile
    me_res = client.get("/api/admin/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "superadmin@bursar.co.ke"
    assert me_res.json()["role"] == "superadmin"

    # 3. Logout
    logout_res = client.post("/api/admin/auth/logout")
    assert logout_res.status_code == 200

    # 4. Profile access after logout fails
    me_after = client.get("/api/admin/auth/me")
    assert me_after.status_code == 401
