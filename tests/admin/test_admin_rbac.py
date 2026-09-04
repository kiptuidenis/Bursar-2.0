import pytest
from fastapi import FastAPI, APIRouter, Depends
from fastapi.testclient import TestClient
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2
from app.api.dependencies import get_current_admin_user, require_admin_roles
from app.api.routers.admin.auth import router as admin_auth_router

# Create test app with admin auth and RBAC routes
test_app = FastAPI()
test_app.include_router(admin_auth_router)

test_rbac_router = APIRouter(prefix="/api/test-rbac", tags=["Test RBAC"])

@test_rbac_router.get("/any-admin")
def any_admin_endpoint(admin: dict = Depends(get_current_admin_user)):
    return {"message": "Hello Admin", "role": admin["role"]}

@test_rbac_router.get("/superadmin-only")
def superadmin_only_endpoint(admin: dict = Depends(require_admin_roles(["superadmin"]))):
    return {"message": "Hello SuperAdmin", "role": admin["role"]}

@test_rbac_router.get("/finops-or-superadmin")
def finops_endpoint(admin: dict = Depends(require_admin_roles(["superadmin", "finops"]))):
    return {"message": "Hello FinOps", "role": admin["role"]}

@test_rbac_router.get("/support-or-superadmin")
def support_endpoint(admin: dict = Depends(require_admin_roles(["superadmin", "support"]))):
    return {"message": "Hello Support", "role": admin["role"]}

@test_rbac_router.get("/auditor-or-superadmin")
def auditor_endpoint(admin: dict = Depends(require_admin_roles(["superadmin", "auditor"]))):
    return {"message": "Hello Auditor", "role": admin["role"]}

test_app.include_router(test_rbac_router)

@pytest.fixture
def rbac_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_rbac.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # Seed admins with different roles
    roles = ["superadmin", "finops", "support", "auditor"]
    for r in roles:
        pwd_hash = hash_password_argon2(f"{r.capitalize()}!Pass2026")
        db.create_admin_user(
            email=f"{r}@bursar.co.ke",
            password_hash=pwd_hash,
            salt="argon2",
            role=r
        )

    db.close()
    with TestClient(test_app) as client:
        yield client

def login_as_role(client: TestClient, role: str):
    """Helper to log in as an administrator of a specific role."""
    res = client.post("/api/admin/auth/login", json={
        "email": f"{role}@bursar.co.ke",
        "password": f"{role.capitalize()}!Pass2026"
    })
    assert res.status_code == 200

def test_unauthenticated_admin_access_rejected(rbac_client):
    """Endpoints protected by get_current_admin_user reject unauthenticated requests with 401."""
    res = rbac_client.get("/api/test-rbac/any-admin")
    assert res.status_code == 401
    assert "Admin authentication session required" in res.json()["detail"]

def test_invalid_or_expired_admin_session_token(rbac_client):
    """Invalid admin session cookie returns 401."""
    rbac_client.cookies.set("admin_session_token", "invalid_fake_token_123")
    res = rbac_client.get("/api/test-rbac/any-admin")
    assert res.status_code == 401
    assert "expired or invalid" in res.json()["detail"].lower()

def test_superadmin_role_access(rbac_client):
    """SuperAdmin has access to all protected endpoints."""
    login_as_role(rbac_client, "superadmin")

    assert rbac_client.get("/api/test-rbac/any-admin").status_code == 200
    assert rbac_client.get("/api/test-rbac/superadmin-only").status_code == 200
    assert rbac_client.get("/api/test-rbac/finops-or-superadmin").status_code == 200
    assert rbac_client.get("/api/test-rbac/support-or-superadmin").status_code == 200
    assert rbac_client.get("/api/test-rbac/auditor-or-superadmin").status_code == 200

def test_finops_role_access_and_forbidden_routes(rbac_client):
    """FinOps has access to finops routes, but is forbidden from superadmin-only or support-only routes."""
    login_as_role(rbac_client, "finops")

    # Allowed
    assert rbac_client.get("/api/test-rbac/any-admin").status_code == 200
    assert rbac_client.get("/api/test-rbac/finops-or-superadmin").status_code == 200

    # Forbidden (403)
    res_super = rbac_client.get("/api/test-rbac/superadmin-only")
    assert res_super.status_code == 403
    assert "Access forbidden" in res_super.json()["detail"]

    res_support = rbac_client.get("/api/test-rbac/support-or-superadmin")
    assert res_support.status_code == 403

def test_support_role_access_and_forbidden_routes(rbac_client):
    """Support has access to support routes, but cannot access financial or superadmin-only routes."""
    login_as_role(rbac_client, "support")

    # Allowed
    assert rbac_client.get("/api/test-rbac/any-admin").status_code == 200
    assert rbac_client.get("/api/test-rbac/support-or-superadmin").status_code == 200

    # Forbidden (403)
    assert rbac_client.get("/api/test-rbac/superadmin-only").status_code == 403
    assert rbac_client.get("/api/test-rbac/finops-or-superadmin").status_code == 403

def test_auditor_role_access_and_forbidden_routes(rbac_client):
    """Auditor has access to auditor routes, but cannot access mutation routes."""
    login_as_role(rbac_client, "auditor")

    # Allowed
    assert rbac_client.get("/api/test-rbac/any-admin").status_code == 200
    assert rbac_client.get("/api/test-rbac/auditor-or-superadmin").status_code == 200

    # Forbidden (403)
    assert rbac_client.get("/api/test-rbac/superadmin-only").status_code == 403
    assert rbac_client.get("/api/test-rbac/finops-or-superadmin").status_code == 403
    assert rbac_client.get("/api/test-rbac/support-or-superadmin").status_code == 403
