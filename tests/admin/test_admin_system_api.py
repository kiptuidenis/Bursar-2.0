import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def system_admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_system.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # 1. Seed Admins
    admin_pwd_hash = hash_password_argon2("SuperAdmin!Pass2026")
    superadmin_id = db.create_admin_user(
        email="superadmin@bursar.co.ke",
        password_hash=admin_pwd_hash,
        salt="argon2",
        role="superadmin"
    )

    finops_pwd_hash = hash_password_argon2("Finops!Pass2026")
    finops_id = db.create_admin_user(
        email="finops@bursar.co.ke",
        password_hash=finops_pwd_hash,
        salt="argon2",
        role="finops"
    )

    support_pwd_hash = hash_password_argon2("Support!Pass2026")
    db.create_admin_user(
        email="support@bursar.co.ke",
        password_hash=support_pwd_hash,
        salt="argon2",
        role="support"
    )

    db.close()

    with TestClient(app) as client:
        # Log in as SuperAdmin by default
        client.post("/api/admin/auth/login", json={
            "email": "superadmin@bursar.co.ke",
            "password": "SuperAdmin!Pass2026"
        })
        yield client, superadmin_id, finops_id

def test_get_system_health(system_admin_client):
    """Admin can query platform health status and gateway mode."""
    client, _, _ = system_admin_client

    res = client.get("/api/admin/system/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["database"] == "connected"
    assert "scheduler" in data
    assert "payment_gateway" in data

def test_superadmin_list_admin_accounts(system_admin_client):
    """SuperAdmin can retrieve list of staff accounts."""
    client, _, _ = system_admin_client

    res = client.get("/api/admin/system/admins")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 3
    emails = [a["email"] for a in data["admins"]]
    assert "superadmin@bursar.co.ke" in emails
    assert "finops@bursar.co.ke" in emails

def test_superadmin_create_staff_account(system_admin_client):
    """SuperAdmin can provision a new staff administrator."""
    client, _, _ = system_admin_client

    res = client.post("/api/admin/system/admins", json={
        "email": "new_auditor@bursar.co.ke",
        "password": "Secure!Password2026",
        "role": "auditor",
        "reason": "Onboarding new compliance officer"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["admin"]["email"] == "new_auditor@bursar.co.ke"
    assert data["admin"]["role"] == "auditor"

def test_superadmin_update_admin_role(system_admin_client):
    """SuperAdmin can update the RBAC role of a staff administrator."""
    client, _, finops_id = system_admin_client

    res = client.put(f"/api/admin/system/admins/{finops_id}/role", json={
        "role": "support",
        "reason": "Temporary department transfer"
    })
    assert res.status_code == 200
    assert res.json()["role"] == "support"

def test_superadmin_toggle_admin_active_status(system_admin_client):
    """SuperAdmin can deactivate and reactivate staff accounts."""
    client, _, finops_id = system_admin_client

    # 1. Deactivate
    res_deact = client.post(f"/api/admin/system/admins/{finops_id}/toggle-active", json={
        "is_active": False,
        "reason": "Staff on extended leave"
    })
    assert res_deact.status_code == 200
    assert res_deact.json()["is_active"] is False

    # 2. Reactivate
    res_react = client.post(f"/api/admin/system/admins/{finops_id}/toggle-active", json={
        "is_active": True,
        "reason": "Staff returned from leave"
    })
    assert res_react.status_code == 200
    assert res_react.json()["is_active"] is True

def test_non_superadmin_forbidden_from_admin_management(system_admin_client):
    """Non-superadmin roles receive 403 Forbidden on admin directory mutations."""
    client, _, finops_id = system_admin_client

    # Log out and log in as FinOps
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "finops@bursar.co.ke",
        "password": "Finops!Pass2026"
    })

    # FinOps CAN view health (200)
    assert client.get("/api/admin/system/health").status_code == 200

    # FinOps CANNOT list admins (403)
    assert client.get("/api/admin/system/admins").status_code == 403

    # FinOps CANNOT create admin (403)
    assert client.post("/api/admin/system/admins", json={
        "email": "hacked@bursar.co.ke",
        "password": "password123",
        "role": "superadmin"
    }).status_code == 403
