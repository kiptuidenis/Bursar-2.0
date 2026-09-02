import pytest
import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2
from app.core.csrf import generate_csrf_token

@pytest.fixture
def admin_exact_time_env(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_exact_timestamps.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # Create admin
    admin_pwd_hash = hash_password_argon2("SuperAdmin!Pass2026")
    admin_id = db.create_admin_user(
        email="superadmin@bursar.co.ke",
        password_hash=admin_pwd_hash,
        salt="argon2",
        role="superadmin"
    )

    # Create user
    user_pwd_hash = hash_password_argon2("User!Pass2026")
    user_id = db.create_user_email(
        email="time_audit_user@example.com",
        password_hash=user_pwd_hash,
        salt="argon2",
        phone_number="254711999888"
    )
    db.update_profile(user_id, first_name="Grace", last_name="Moraa")

    # Seed deposits:
    # 1. Completed deposit via status update
    d1 = db.create_deposit(user_id=user_id, amount=1500, checkout_request_id="ws_CO_001_TIME")
    eat_time_d1 = "2026-09-02 14:35:22"
    db.update_deposit_status("ws_CO_001_TIME", status="COMPLETED", mpesa_receipt="QWE123RTY", completed_at=eat_time_d1)

    # 2. Pending deposit
    d2 = db.create_deposit(user_id=user_id, amount=2000, checkout_request_id="ws_CO_002_PENDING")

    # Seed payouts:
    # 1. Completed payout with completed_at
    p1 = db.create_payout(
        user_id=user_id,
        payout_date="2026-09-01",
        amount=500,
        phone_number="254711999888",
        status="COMPLETED",
        conversation_id="conv_p1_time",
        originator_conversation_id="orig_p1_time"
    )
    eat_time_p1 = "2026-09-01 08:00:15"
    db.update_payout_status("conv_p1_time", status="COMPLETED", transaction_id="MPESA_TX_TIME_01", completed_at=eat_time_p1)

    # 2. Failed payout with failed_at
    p2 = db.create_payout(
        user_id=user_id,
        payout_date="2026-09-02",
        amount=500,
        phone_number="254711999888",
        status="FAILED",
        conversation_id="conv_p2_failed",
        originator_conversation_id="orig_p2_failed"
    )
    eat_time_p2 = "2026-09-02 08:00:25"
    db.update_payout_status("conv_p2_failed", status="FAILED", error_message="Insufficient float", failed_at=eat_time_p2)

    db.close()

    with TestClient(app) as client:
        # Log in as admin
        login_res = client.post("/api/admin/auth/login", json={
            "email": "superadmin@bursar.co.ke",
            "password": "SuperAdmin!Pass2026"
        })
        assert login_res.status_code == 200

        csrf = generate_csrf_token()
        client.cookies.set("csrf_token", csrf)
        client.headers["X-CSRF-Token"] = csrf

        yield client, user_id, test_db_path

def test_admin_deposits_list_contains_exact_timestamps(admin_exact_time_env):
    """Admin deposits list returns created_at ISO string with UTC indicator and exact completed_at timestamp."""
    client, user_id, db_path = admin_exact_time_env

    res = client.get("/api/admin/deposits")
    assert res.status_code == 200
    data = res.json()
    deposits = data["deposits"]
    assert len(deposits) == 2

    # Find completed deposit
    comp_dep = next(d for d in deposits if d["checkout_request_id"] == "ws_CO_001_TIME")
    assert comp_dep["status"] == "COMPLETED"
    assert comp_dep["mpesa_receipt"] == "QWE123RTY"
    assert comp_dep["completed_at"] == "2026-09-02 14:35:22"
    assert "created_at" in comp_dep and comp_dep["created_at"]
    assert comp_dep["created_at"].endswith("Z") or "+" in comp_dep["created_at"]

    # Find pending deposit
    pend_dep = next(d for d in deposits if d["checkout_request_id"] == "ws_CO_002_PENDING")
    assert pend_dep["status"] == "PENDING"
    assert pend_dep["completed_at"] == ""
    assert "created_at" in pend_dep and pend_dep["created_at"]

def test_admin_payouts_list_contains_exact_timestamps(admin_exact_time_env):
    """Admin payouts list returns exact completed_at and failed_at timestamps."""
    client, user_id, db_path = admin_exact_time_env

    res = client.get("/api/admin/payouts")
    assert res.status_code == 200
    data = res.json()
    payouts = data["payouts"]
    assert len(payouts) == 2

    # Find completed payout
    comp_payout = next(p for p in payouts if p["conversation_id"] == "conv_p1_time")
    assert comp_payout["status"] == "COMPLETED"
    assert comp_payout["completed_at"] == "2026-09-01 08:00:15"
    assert "created_at" in comp_payout and comp_payout["created_at"]

    # Find failed payout
    failed_payout = next(p for p in payouts if p["conversation_id"] == "conv_p2_failed")
    assert failed_payout["status"] == "FAILED"
    assert failed_payout["failed_at"] == "2026-09-02 08:00:25"
    assert "created_at" in failed_payout and failed_payout["created_at"]

def test_admin_manual_settle_deposit_stamps_exact_completed_at(admin_exact_time_env):
    """Manually settling a pending deposit stamps completed_at with current timestamp."""
    client, user_id, db_path = admin_exact_time_env

    res = client.post(
        "/api/admin/deposits/ws_CO_002_PENDING/manual-settle",
        json={
            "mpesa_receipt": "REC999SETTLE",
            "reason": "Customer called support with M-Pesa confirmation message."
        }
    )
    assert res.status_code == 200

    # Verify via deposits list API
    dep_res = client.get("/api/admin/deposits")
    assert dep_res.status_code == 200
    deposits = dep_res.json()["deposits"]
    settled = next(d for d in deposits if d["checkout_request_id"] == "ws_CO_002_PENDING")
    assert settled["status"] == "COMPLETED"
    assert settled["mpesa_receipt"] == "REC999SETTLE"
    assert settled["completed_at"] != ""
    # Verify completed_at format YYYY-MM-DD HH:MM:SS
    assert len(settled["completed_at"].split(" ")) == 2
