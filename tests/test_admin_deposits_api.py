import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def deposits_admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_deposits.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # 1. Seed Admins
    admin_pwd_hash = hash_password_argon2("SuperAdmin!Pass2026")
    db.create_admin_user(
        email="superadmin@bursar.co.ke",
        password_hash=admin_pwd_hash,
        salt="argon2",
        role="superadmin"
    )

    finops_pwd_hash = hash_password_argon2("Finops!Pass2026")
    db.create_admin_user(
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

    auditor_pwd_hash = hash_password_argon2("Auditor!Pass2026")
    db.create_admin_user(
        email="auditor@bursar.co.ke",
        password_hash=auditor_pwd_hash,
        salt="argon2",
        role="auditor"
    )

    # 2. Seed Customer User
    user_pwd_hash = hash_password_argon2("User!Pass2026")
    user_id = db.create_user_email(
        email="deposit_user@example.com",
        password_hash=user_pwd_hash,
        salt="argon2",
        phone_number="254711888001"
    )
    db.update_profile(user_id, first_name="Eunice", last_name="Njeri")
    db.adjust_balance(user_id, 3000)

    # 3. Seed Deposits
    # Completed deposit
    dep1 = db.create_deposit(user_id, "chk_comp_1001", 3000)
    db.update_deposit_status("chk_comp_1001", status="COMPLETED", mpesa_receipt="QWE123RTY")

    # Stuck Pending deposit
    dep2 = db.create_deposit(user_id, "chk_pend_2002", 5000)

    # Failed deposit
    dep3 = db.create_deposit(user_id, "chk_fail_3003", 2000)
    db.update_deposit_status("chk_fail_3003", status="FAILED")

    db.close()

    with TestClient(app) as client:
        # Log in as FinOps by default
        client.post("/api/admin/auth/login", json={
            "email": "finops@bursar.co.ke",
            "password": "Finops!Pass2026"
        })
        yield client, user_id

def test_admin_list_deposits(deposits_admin_client):
    """Admin can list deposits with filtering by status and search."""
    client, user_id = deposits_admin_client

    # 1. List all deposits
    res_all = client.get("/api/admin/deposits")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total"] == 3
    assert data_all["total_amount"] == 10000

    # 2. Filter by status=COMPLETED
    res_comp = client.get("/api/admin/deposits?status=COMPLETED")
    assert res_comp.status_code == 200
    assert res_comp.json()["total"] == 1
    assert res_comp.json()["deposits"][0]["checkout_request_id"] == "chk_comp_1001"

    # 3. Filter by status=PENDING
    res_pend = client.get("/api/admin/deposits?status=PENDING")
    assert res_pend.status_code == 200
    assert res_pend.json()["total"] == 1
    assert res_pend.json()["deposits"][0]["checkout_request_id"] == "chk_pend_2002"

    # 4. Search by M-Pesa receipt
    res_search = client.get("/api/admin/deposits?search=QWE123RTY")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1

def test_admin_manual_settle_pending_deposit(deposits_admin_client):
    """FinOps admin can manually settle a stuck pending deposit and credit user wallet."""
    client, user_id = deposits_admin_client

    res_settle = client.post("/api/admin/deposits/chk_pend_2002/manual-settle", json={
        "mpesa_receipt": "REC998877MAN",
        "reason": "Confirmed funds in Safaricom Till statement manually"
    })
    assert res_settle.status_code == 200
    data = res_settle.json()
    assert data["status"] == "success"
    assert data["mpesa_receipt"] == "REC998877MAN"
    assert data["new_balance"] == 8000  # 3000 previous + 5000 deposit

    # Verify deposit is now COMPLETED
    res_list = client.get("/api/admin/deposits?status=COMPLETED")
    receipts = [d["mpesa_receipt"] for d in res_list.json()["deposits"]]
    assert "REC998877MAN" in receipts

def test_admin_manual_settle_already_completed_rejected(deposits_admin_client):
    """Attempting to manually settle an already completed deposit fails with 400."""
    client, _ = deposits_admin_client

    res = client.post("/api/admin/deposits/chk_comp_1001/manual-settle", json={
        "mpesa_receipt": "DUPLICATE_REC",
        "reason": "Attempting double settlement"
    })
    assert res.status_code == 400
    assert "already completed" in res.json()["detail"].lower()

def test_admin_requery_deposit_status(deposits_admin_client):
    """Admin can requery payment gateway for deposit status."""
    client, user_id = deposits_admin_client

    # Mock gateway response to simulate completed payment
    with patch("app.api.routers.admin.deposits.check_stk_status") as mock_check:
        mock_check.return_value = {
            "status": "SUCCESS",
            "mpesa_reference": "INTA_MOCK_REC_1"
        }
        res_req = client.post("/api/admin/deposits/chk_pend_2002/requery")
        assert res_req.status_code == 200
        assert res_req.json()["status"] == "COMPLETED"
        assert res_req.json()["mpesa_receipt"] == "INTA_MOCK_REC_1"

def test_support_and_auditor_roles_forbidden_from_deposit_mutations(deposits_admin_client):
    """Support and Auditor roles cannot manually settle deposits."""
    client, _ = deposits_admin_client

    # 1. Switch to Support
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "support@bursar.co.ke",
        "password": "Support!Pass2026"
    })

    # Support CAN view deposits (200)
    assert client.get("/api/admin/deposits").status_code == 200

    # Support CANNOT manual-settle deposits (403)
    res_settle = client.post("/api/admin/deposits/chk_pend_2002/manual-settle", json={
        "mpesa_receipt": "SUPP_REC",
        "reason": "Unauthorized support attempt"
    })
    assert res_settle.status_code == 403

    # 2. Switch to Auditor
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "auditor@bursar.co.ke",
        "password": "Auditor!Pass2026"
    })

    # Auditor CAN view deposits (200)
    assert client.get("/api/admin/deposits").status_code == 200

    # Auditor CANNOT manual-settle (403)
    assert client.post("/api/admin/deposits/chk_pend_2002/manual-settle", json={
        "mpesa_receipt": "AUD_REC",
        "reason": "Auditor attempt"
    }).status_code == 403
