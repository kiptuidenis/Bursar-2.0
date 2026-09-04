import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def audit_admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_audit.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # 1. Seed Admins
    admin_pwd_hash = hash_password_argon2("SuperAdmin!Pass2026")
    admin_id = db.create_admin_user(
        email="superadmin@bursar.co.ke",
        password_hash=admin_pwd_hash,
        salt="argon2",
        role="superadmin"
    )

    auditor_pwd_hash = hash_password_argon2("Auditor!Pass2026")
    db.create_admin_user(
        email="auditor@bursar.co.ke",
        password_hash=auditor_pwd_hash,
        salt="argon2",
        role="auditor"
    )

    # 2. Seed Sample Audit Logs
    db.create_admin_audit_log(
        admin_id=admin_id,
        action="ADMIN_BALANCE_ADJUSTMENT",
        target_type="User",
        target_id=101,
        before_state='{"balance": 5000}',
        after_state='{"balance": 8000}',
        reason="Manual compensation for M-Pesa network downtime",
        ip_address="192.168.1.50"
    )

    db.create_admin_audit_log(
        admin_id=admin_id,
        action="ADMIN_OVERRIDE_BUDGET_LOCK",
        target_type="User",
        target_id=102,
        before_state='{"budget_locked_until": "2026-08-31"}',
        after_state='{"budget_locked_until": ""}',
        reason="Customer emergency medical expense override",
        ip_address="192.168.1.50"
    )

    db.create_admin_audit_log(
        admin_id=admin_id,
        action="ADMIN_DEPOSIT_MANUAL_SETTLE",
        target_type="Deposit",
        target_id=201,
        before_state='{"status": "PENDING"}',
        after_state='{"status": "COMPLETED", "mpesa_receipt": "REC887766"}',
        reason="Verified funds in Safaricom statement",
        ip_address="192.168.1.50"
    )

    db.close()

    with TestClient(app) as client:
        # Log in as Auditor by default
        client.post("/api/admin/auth/login", json={
            "email": "auditor@bursar.co.ke",
            "password": "Auditor!Pass2026"
        })
        yield client

def test_admin_list_audit_logs(audit_admin_client):
    """Auditor can retrieve paginated list of compliance audit logs."""
    client = audit_admin_client

    res = client.get("/api/admin/audit/logs")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 3
    assert len(data["logs"]) >= 3

def test_admin_filter_audit_logs_by_action(audit_admin_client):
    """Filter audit logs by specific action type."""
    client = audit_admin_client

    res = client.get("/api/admin/audit/logs?action=ADMIN_BALANCE_ADJUSTMENT")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["logs"][0]["action"] == "ADMIN_BALANCE_ADJUSTMENT"
    assert "compensation" in data["logs"][0]["reason"]

def test_admin_search_audit_logs(audit_admin_client):
    """Search audit logs by reason text or IP address."""
    client = audit_admin_client

    res = client.get("/api/admin/audit/logs?search=medical")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["logs"][0]["action"] == "ADMIN_OVERRIDE_BUDGET_LOCK"

def test_admin_export_audit_logs_csv(audit_admin_client):
    """Export compliance audit logs as CSV document."""
    client = audit_admin_client

    res = client.get("/api/admin/audit/export")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=bursar_admin_audit_logs.csv" in res.headers.get("content-disposition", "")
    
    csv_text = res.text
    assert "Log ID,Timestamp,Admin Email,Action,Target Type,Target ID,Reason,IP Address,Before State,After State" in csv_text
    assert "ADMIN_BALANCE_ADJUSTMENT" in csv_text
    assert "ADMIN_OVERRIDE_BUDGET_LOCK" in csv_text
    assert "ADMIN_DEPOSIT_MANUAL_SETTLE" in csv_text

def test_unauthenticated_request_rejected(audit_admin_client):
    """Unauthenticated access to audit endpoints returns 401."""
    client = audit_admin_client
    client.post("/api/admin/auth/logout")

    res_logs = client.get("/api/admin/audit/logs")
    assert res_logs.status_code == 401

    res_export = client.get("/api/admin/audit/export")
    assert res_export.status_code == 401
