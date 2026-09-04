import os
import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_overview.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOW_TEST_ENDPOINTS", "1")

    db = DatabaseManager(test_db_path)
    db.initialize()

    # 1. Seed SuperAdmin
    admin_pwd_hash = hash_password_argon2("SuperAdmin!Pass2026")
    db.create_admin_user(
        email="superadmin@bursar.co.ke",
        password_hash=admin_pwd_hash,
        salt="argon2",
        role="superadmin"
    )

    # 2. Seed Users
    user1_id = db.create_user_email(
        email="user1@example.com",
        password_hash=admin_pwd_hash,
        salt="argon2",
        phone_number="254711000001"
    )
    user2_id = db.create_user_email(
        email="user2@example.com",
        password_hash=admin_pwd_hash,
        salt="argon2",
        phone_number="254711000002"
    )

    # 3. Add Balances & Locks
    db.adjust_balance(user1_id, 5000)
    db.adjust_balance(user2_id, 3000)
    db.lock_budget(user1_id)

    # 4. Seed Completed and Pending Deposits
    dep1 = db.create_deposit(user1_id, "chk_1001", 5000)
    db.update_deposit_status("chk_1001", status="COMPLETED", mpesa_receipt="REC1001")
    
    dep2 = db.create_deposit(user2_id, "chk_1002", 3000)
    db.update_deposit_status("chk_1002", status="COMPLETED", mpesa_receipt="REC1002")

    dep3 = db.create_deposit(user2_id, "chk_1003", 2000)

    # 5. Seed Payouts (completed and failed) for today
    eat_tz = datetime.timezone(datetime.timedelta(hours=3))
    today_str = datetime.datetime.now(eat_tz).strftime("%Y-%m-%d")
    db.create_payout(user1_id, today_str, 1000, "254711000001", status="COMPLETED")
    db.create_payout(user2_id, today_str, 500, "254711000002", status="FAILED")

    db.close()

    with TestClient(app) as client:
        # Log in as admin
        login_res = client.post("/api/admin/auth/login", json={
            "email": "superadmin@bursar.co.ke",
            "password": "SuperAdmin!Pass2026"
        })
        assert login_res.status_code == 200
        yield client

def test_unauthenticated_overview_access_rejected(tmp_path, monkeypatch):
    """Unauthenticated request to /api/admin/overview returns 401."""
    test_db_path = str(tmp_path / "test_unauth_overview.db")
    monkeypatch.setenv("DATABASE_URL", test_db_path)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")

    db = DatabaseManager(test_db_path)
    db.initialize()
    db.close()

    with TestClient(app) as client:
        res = client.get("/api/admin/overview")
        assert res.status_code == 401

def test_admin_overview_metrics_calculation(admin_client):
    """Admin overview calculates platform float, active savers, queues, and activity correctly."""
    res = admin_client.get("/api/admin/overview")
    assert res.status_code == 200
    data = res.json()

    # Float Metrics
    assert data["float"]["total_user_balance"] == 8000
    assert data["float"]["total_platform_float"] == 8000
    assert data["float"]["total_deposited_all_time"] == 8000
    assert data["float"]["total_disbursed_all_time"] == 1000

    # User Metrics
    assert data["users"]["total_registered_users"] == 2
    assert data["users"]["active_locked_savers"] == 1
    assert data["users"]["unlocked_users"] == 1

    # Operations & Queues
    assert data["queues"]["failed_payouts_count"] == 1
    assert data["queues"]["pending_deposits_count"] == 1
    assert data["queues"]["pending_deposits_amount"] == 2000

    # Payout Velocity
    assert data["payout_velocity"]["today_disbursed_amount"] == 1000
    assert data["payout_velocity"]["today_disbursed_count"] == 1

    # System Health
    assert "app_version" in data["system"]
