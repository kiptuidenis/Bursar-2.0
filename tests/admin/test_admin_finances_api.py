import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def finances_admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_finances.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # 1. Seed Admins with various roles
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

    # 2. Seed Customer Users
    user_pwd_hash = hash_password_argon2("User!Pass2026")
    user1_id = db.create_user_email(
        email="saver1@example.com",
        password_hash=user_pwd_hash,
        salt="argon2",
        phone_number="254711999001"
    )
    db.update_profile(user1_id, first_name="Kiptoo", last_name="Cheruiyot")
    db.adjust_balance(user1_id, 15000)
    db.lock_budget(user1_id)
    db.lock_deposit(user1_id)

    user2_id = db.create_user_email(
        email="saver2@example.com",
        password_hash=user_pwd_hash,
        salt="argon2",
        phone_number="254711999002"
    )
    db.update_profile(user2_id, first_name="Grace", last_name="Moraa")
    db.adjust_balance(user2_id, 5000)

    db.close()

    with TestClient(app) as client:
        # Log in as FinOps by default
        client.post("/api/admin/auth/login", json={
            "email": "finops@bursar.co.ke",
            "password": "Finops!Pass2026"
        })
        yield client, user1_id, user2_id

def test_admin_get_wallets_list(finances_admin_client):
    """Admin can view paginated wallets and platform total balance."""
    client, user1_id, user2_id = finances_admin_client

    res = client.get("/api/admin/finances/wallets")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert data["total_platform_balance"] == 20000
    assert len(data["wallets"]) == 2

    # Verify sorting by balance desc
    assert data["wallets"][0]["balance"] == 15000
    assert data["wallets"][0]["email"] == "saver1@example.com"
    assert data["wallets"][1]["balance"] == 5000

def test_admin_adjust_balance_credit_and_debit(finances_admin_client):
    """FinOps admin can credit and debit user wallet with audit trail."""
    client, user1_id, _ = finances_admin_client

    # 1. Credit wallet by 2000
    res_credit = client.post("/api/admin/finances/adjust-balance", json={
        "user_id": user1_id,
        "amount": 2000,
        "adjustment_type": "CREDIT",
        "reason": "Reconciliation of delayed M-Pesa deposit",
        "reference_id": "MPESA_REF_9981"
    })
    assert res_credit.status_code == 200
    data_cr = res_credit.json()
    assert data_cr["previous_balance"] == 15000
    assert data_cr["new_balance"] == 17000

    # 2. Debit wallet by 5000
    res_debit = client.post("/api/admin/finances/adjust-balance", json={
        "user_id": user1_id,
        "amount": 5000,
        "adjustment_type": "DEBIT",
        "reason": "Reversal of erroneous credit adjustment",
        "reference_id": "REV_9981"
    })
    assert res_debit.status_code == 200
    data_db = res_debit.json()
    assert data_db["previous_balance"] == 17000
    assert data_db["new_balance"] == 12000

def test_admin_adjust_balance_insufficient_funds_rejected(finances_admin_client):
    """Debit adjustment exceeding wallet balance is rejected with 400."""
    client, _, user2_id = finances_admin_client

    res = client.post("/api/admin/finances/adjust-balance", json={
        "user_id": user2_id,
        "amount": 10000,  # balance is only 5000
        "adjustment_type": "DEBIT",
        "reason": "Attempting excess debit"
    })
    assert res.status_code == 400
    assert "insufficient" in res.json()["detail"].lower()

def test_admin_override_deposit_and_budget_locks(finances_admin_client):
    """FinOps admin can release deposit and budget locks in emergency."""
    client, user1_id, _ = finances_admin_client

    # 1. Release Deposit Lock
    res_dep = client.post(f"/api/admin/finances/{user1_id}/override-deposit-lock", json={
        "reason": "Customer emergency medical withdrawal request"
    })
    assert res_dep.status_code == 200
    assert res_dep.json()["status"] == "success"

    # 2. Release Budget Lock
    res_bud = client.post(f"/api/admin/finances/{user1_id}/override-budget-lock", json={
        "reason": "Customer requested mid-month plan restructure"
    })
    assert res_bud.status_code == 200
    assert res_bud.json()["status"] == "success"

    # Verify locks released in 360 view
    res_360 = client.get(f"/api/admin/users/{user1_id}")
    assert res_360.json()["wallet"]["is_budget_locked"] is False
    assert res_360.json()["wallet"]["is_deposit_locked"] is False

def test_support_and_auditor_roles_forbidden_from_financial_mutations(finances_admin_client):
    """Support and Auditor roles cannot execute balance adjustments or lock overrides."""
    client, user1_id, _ = finances_admin_client

    # 1. Switch to Support
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "support@bursar.co.ke",
        "password": "Support!Pass2026"
    })

    # Support forbidden from balance adjustment (403)
    res_adj = client.post("/api/admin/finances/adjust-balance", json={
        "user_id": user1_id,
        "amount": 1000,
        "adjustment_type": "CREDIT",
        "reason": "Unauthorized support attempt"
    })
    assert res_adj.status_code == 403

    # Support forbidden from lock overrides (403)
    assert client.post(f"/api/admin/finances/{user1_id}/override-deposit-lock", json={"reason": "test"}).status_code == 403
    assert client.post(f"/api/admin/finances/{user1_id}/override-budget-lock", json={"reason": "test"}).status_code == 403

    # 2. Switch to Auditor
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "auditor@bursar.co.ke",
        "password": "Auditor!Pass2026"
    })

    # Auditor CAN view wallets (200)
    assert client.get("/api/admin/finances/wallets").status_code == 200

    # Auditor CANNOT adjust balance (403)
    assert client.post("/api/admin/finances/adjust-balance", json={
        "user_id": user1_id,
        "amount": 1000,
        "adjustment_type": "CREDIT",
        "reason": "Auditor attempt"
    }).status_code == 403
