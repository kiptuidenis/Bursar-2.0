import io
import csv
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def audit_system_admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_audit_system.db")
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
    support_id = db.create_admin_user(
        email="support@bursar.co.ke",
        password_hash=support_pwd_hash,
        salt="argon2",
        role="support"
    )

    auditor_pwd_hash = hash_password_argon2("Auditor!Pass2026")
    auditor_id = db.create_admin_user(
        email="auditor@bursar.co.ke",
        password_hash=auditor_pwd_hash,
        salt="argon2",
        role="auditor"
    )

    # 2. Seed Audit Logs
    db.create_admin_audit_log(
        admin_id=superadmin_id,
        action="ADMIN_FINANCIAL_ADJUSTMENT",
        target_type="User",
        target_id=101,
        before_state='{"balance": 1000}',
        after_state='{"balance": 5000}',
        reason="Manual adjustment",
        ip_address="192.168.1.10"
    )
    db.create_admin_audit_log(
        admin_id=finops_id,
        action="ADMIN_USER_UNLOCK",
        target_type="User",
        target_id=102,
        reason="Customer requested password unlock",
        ip_address="192.168.1.20"
    )
    db.create_admin_audit_log(
        admin_id=superadmin_id,
        action="ADMIN_SYSTEM_CONFIG_CHANGE",
        target_type="System",
        target_id=0,
        reason="Updated timeout values",
        ip_address="192.168.1.10"
    )

    db.close()

    with TestClient(app) as client:
        # Log in as Superadmin by default
        client.post("/api/admin/auth/login", json={
            "email": "superadmin@bursar.co.ke",
            "password": "SuperAdmin!Pass2026"
        })
        yield client, superadmin_id, finops_id, support_id, auditor_id

def test_admin_list_audit_logs(audit_system_admin_client):
    """Admin can query paginated audit logs with action and search filtering."""
    client, superadmin_id, finops_id, _, _ = audit_system_admin_client

    # 1. List all audit logs
    res_all = client.get("/api/admin/audit/logs")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total"] >= 3
    assert len(data_all["logs"]) >= 3

    # 2. Filter by action
    res_action = client.get("/api/admin/audit/logs?action=ADMIN_USER_UNLOCK")
    assert res_action.status_code == 200
    assert res_action.json()["total"] == 1
    assert res_action.json()["logs"][0]["action"] == "ADMIN_USER_UNLOCK"

    # 3. Search by reason keyword
    res_search = client.get("/api/admin/audit/logs?search=timeout")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1
    assert res_search.json()["logs"][0]["action"] == "ADMIN_SYSTEM_CONFIG_CHANGE"

def test_admin_export_audit_logs_csv(audit_system_admin_client):
    """Admin can export compliance audit trail as CSV."""
    client, _, _, _, _ = audit_system_admin_client

    res = client.get("/api/admin/audit/export")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]

    csv_reader = csv.reader(io.StringIO(res.text))
    rows = list(csv_reader)
    assert len(rows) >= 4  # Header + records
    header = rows[0]
    assert "Action" in header
    assert "Admin Email" in header
    assert "Reason" in header


def test_admin_system_health(audit_system_admin_client):
    """Admin can inspect system health and runtime status."""
    client, _, _, _, _ = audit_system_admin_client

    res = client.get("/api/admin/system/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "scheduler" in data
    assert "payment_gateway" in data

def test_superadmin_manage_admin_accounts(audit_system_admin_client):
    """SuperAdmin can list admin accounts and toggle active status."""
    client, superadmin_id, finops_id, _, _ = audit_system_admin_client

    # 1. List all admins
    res_list = client.get("/api/admin/system/admins")
    assert res_list.status_code == 200
    admins = res_list.json()["admins"]
    assert len(admins) == 4

    # 2. Deactivate finops admin
    res_deact = client.post(f"/api/admin/system/admins/{finops_id}/toggle-active", json={
        "is_active": False,
        "reason": "Staff member on leave"
    })
    assert res_deact.status_code == 200
    assert res_deact.json()["is_active"] is False

    # 3. SuperAdmin cannot deactivate self
    res_self = client.post(f"/api/admin/system/admins/{superadmin_id}/toggle-active", json={
        "is_active": False,
        "reason": "Accidental self-deactivation"
    })
    assert res_self.status_code == 400
    assert "cannot deactivate your own" in res_self.json()["detail"].lower()

def test_rbac_admin_management_restricted_to_superadmin(audit_system_admin_client):
    """Non-superadmin roles cannot access or mutate admin user accounts."""
    client, _, finops_id, support_id, auditor_id = audit_system_admin_client

    # 1. FinOps role cannot access /admins (403)
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "finops@bursar.co.ke",
        "password": "Finops!Pass2026"
    })
    assert client.get("/api/admin/system/admins").status_code == 403
    assert client.post(f"/api/admin/system/admins/{support_id}/toggle-active", json={"is_active": False, "reason": "test"}).status_code == 403

    # 2. Auditor CAN view audit logs (200) but CANNOT access /admins (403)
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "auditor@bursar.co.ke",
        "password": "Auditor!Pass2026"
    })
    assert client.get("/api/admin/audit/logs").status_code == 200
    assert client.get("/api/admin/audit/export").status_code == 200
    assert client.get("/api/admin/system/admins").status_code == 403
