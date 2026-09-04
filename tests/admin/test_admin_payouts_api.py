import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def payouts_admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_payouts.db")
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
        email="payout_user@example.com",
        password_hash=user_pwd_hash,
        salt="argon2",
        phone_number="254711777001"
    )
    db.update_profile(user_id, first_name="Dennis", last_name="Rotich")
    db.adjust_balance(user_id, 10000)

    # 3. Seed Payouts
    # Completed payout
    p1 = db.create_payout(
        user_id=user_id,
        payout_date="2026-08-28",
        amount=500,
        phone_number="254711777001",
        status="COMPLETED",
        conversation_id="conv_p1_1001",
        originator_conversation_id="orig_p1_1001"
    )
    db.update_payout_status("conv_p1_1001", status="COMPLETED", transaction_id="MPESA_TX_9001")

    # Failed payout
    p2 = db.create_payout(
        user_id=user_id,
        payout_date="2026-08-29",
        amount=500,
        phone_number="254711777001",
        status="FAILED",
        conversation_id="conv_p2_2002",
        originator_conversation_id="orig_p2_2002"
    )

    # Pending payout
    p3 = db.create_payout(
        user_id=user_id,
        payout_date="2026-08-30",
        amount=500,
        phone_number="254711777001",
        status="PENDING",
        conversation_id="conv_p3_3003",
        originator_conversation_id="orig_p3_3003"
    )

    db.close()

    with TestClient(app) as client:
        # Log in as FinOps by default
        client.post("/api/admin/auth/login", json={
            "email": "finops@bursar.co.ke",
            "password": "Finops!Pass2026"
        })
        yield client, user_id, p1, p2, p3

def test_admin_list_payouts(payouts_admin_client):
    """Admin can list payouts with filtering by status and search."""
    client, user_id, p1, p2, p3 = payouts_admin_client

    # 1. List all payouts
    res_all = client.get("/api/admin/payouts")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total"] == 3
    assert data_all["total_disbursed"] >= 500

    # 2. Filter by status=FAILED
    res_fail = client.get("/api/admin/payouts?status=FAILED")
    assert res_fail.status_code == 200
    assert res_fail.json()["total"] == 1
    assert res_fail.json()["payouts"][0]["id"] == p2

    # 3. Search by conversation ID
    res_search = client.get("/api/admin/payouts?search=conv_p1_1001")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1

def test_admin_retry_failed_payout(payouts_admin_client):
    """FinOps admin can retry a failed payout with simulated gateway response."""
    client, user_id, _, p2, _ = payouts_admin_client

    with patch("app.api.routers.admin.payouts.send_b2c_payout", new_callable=AsyncMock) as mock_b2c:
        mock_b2c.return_value = {
            "status": "PENDING",
            "conversation_id": "RETRY_CONV_9988",
            "tracking_id": "TRACK_9988"
        }
        res_retry = client.post(f"/api/admin/payouts/{p2}/retry", json={
            "reason": "Retrying failed B2C transaction after Safaricom maintenance"
        })
        assert res_retry.status_code == 200
        assert res_retry.json()["status"] == "success"

def test_admin_manual_settle_payout(payouts_admin_client):
    """FinOps admin can manually mark a failed or pending payout as settled."""
    client, user_id, _, _, p3 = payouts_admin_client

    res_settle = client.post(f"/api/admin/payouts/{p3}/mark-settled", json={
        "transaction_id": "MPESA_MANUAL_TX_7766",
        "reason": "Disbursed manually via business bank account"
    })
    assert res_settle.status_code == 200
    data = res_settle.json()
    assert data["status"] == "success"
    assert data["transaction_id"] == "MPESA_MANUAL_TX_7766"

def test_admin_manual_settle_already_completed_rejected(payouts_admin_client):
    """Attempting to mark an already completed payout as settled returns 400."""
    client, _, p1, _, _ = payouts_admin_client

    res = client.post(f"/api/admin/payouts/{p1}/mark-settled", json={
        "transaction_id": "DUPLICATE_TX",
        "reason": "Attempting double settlement"
    })
    assert res.status_code == 400
    assert "already completed" in res.json()["detail"].lower()

def test_admin_trigger_daily_batch(payouts_admin_client):
    """Admin can trigger daily payout scheduler batch manually."""
    client, _, _, _, _ = payouts_admin_client

    with patch("app.api.routers.admin.payouts.process_daily_payouts_batch", new_callable=AsyncMock) as mock_batch:
        mock_batch.return_value = {"processed": 1, "succeeded": 1, "failed": 0}
        res = client.post("/api/admin/payouts/trigger-daily-batch")
        assert res.status_code == 200
        assert res.json()["status"] == "success"

def test_support_and_auditor_roles_forbidden_from_payout_mutations(payouts_admin_client):
    """Support and Auditor roles cannot retry or manually settle payouts."""
    client, _, _, p2, p3 = payouts_admin_client

    # 1. Switch to Support
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "support@bursar.co.ke",
        "password": "Support!Pass2026"
    })

    # Support CAN view payouts (200)
    assert client.get("/api/admin/payouts").status_code == 200

    # Support CANNOT retry payout (403)
    assert client.post(f"/api/admin/payouts/{p2}/retry", json={"reason": "Support attempt"}).status_code == 403

    # Support CANNOT manual-settle payout (403)
    assert client.post(f"/api/admin/payouts/{p3}/mark-settled", json={"transaction_id": "TX", "reason": "test"}).status_code == 403

    # Support CANNOT trigger batch (403)
    assert client.post("/api/admin/payouts/trigger-daily-batch").status_code == 403

    # 2. Switch to Auditor
    client.post("/api/admin/auth/logout")
    client.post("/api/admin/auth/login", json={
        "email": "auditor@bursar.co.ke",
        "password": "Auditor!Pass2026"
    })

    # Auditor CAN view payouts (200)
    assert client.get("/api/admin/payouts").status_code == 200

    # Auditor CANNOT mutate (403)
    assert client.post(f"/api/admin/payouts/{p2}/retry", json={"reason": "Auditor attempt"}).status_code == 403
