import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2

@pytest.fixture
def users_admin_client(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_admin_users.db")
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

    # 2. Seed Users
    user_pwd_hash = hash_password_argon2("User!Password2026")
    user1_id = db.create_user_email(
        email="alice@example.com",
        password_hash=user_pwd_hash,
        salt="argon2",
        phone_number="254711111111"
    )
    db.update_profile(user1_id, first_name="Alice", last_name="Wanjiku")
    db.adjust_balance(user1_id, 10000)
    db.lock_budget(user1_id)
    db.create_deposit(user1_id, "chk_alice_1", 10000)
    db.update_deposit_status("chk_alice_1", status="COMPLETED", mpesa_receipt="REC_ALICE_1")
    db.create_payout(user1_id, "2026-08-30", 500, "254711111111", status="COMPLETED")
    db.create_session_db(user1_id, "alice_tok_1", "Chrome", "127.0.0.1", 9999999999)

    user2_id = db.create_user_email(
        email="bob@example.com",
        password_hash=user_pwd_hash,
        salt="argon2",
        phone_number="254722222222"
    )
    db.update_profile(user2_id, first_name="Bob", last_name="Otieno")
    # Lock out Bob by simulating 5 failed attempts
    for _ in range(5):
        db.record_failed_login_attempt("bob@example.com")

    db.close()

    with TestClient(app) as client:
        # Default login as superadmin
        client.post("/api/admin/auth/login", json={
            "email": "superadmin@bursar.co.ke",
            "password": "SuperAdmin!Pass2026"
        })
        yield client, user1_id, user2_id

def test_admin_list_users_pagination_and_search(users_admin_client):
    """Admin can list and search users across email, phone, and name."""
    client, user1_id, user2_id = users_admin_client

    # 1. Search by name "Alice"
    res_alice = client.get("/api/admin/users?search=Alice")
    assert res_alice.status_code == 200
    data_alice = res_alice.json()
    assert data_alice["total"] == 1
    assert data_alice["users"][0]["email"] == "alice@example.com"
    assert data_alice["users"][0]["balance"] == 10000
    assert data_alice["users"][0]["is_budget_locked"] is True

    # 2. Search by phone
    res_phone = client.get("/api/admin/users?search=254722222222")
    assert res_phone.status_code == 200
    assert res_phone.json()["total"] == 1
    assert res_phone.json()["users"][0]["email"] == "bob@example.com"

    # 3. Filter by locked_out status
    res_locked = client.get("/api/admin/users?status_filter=locked_out")
    assert res_locked.status_code == 200
    assert res_locked.json()["total"] == 1
    assert res_locked.json()["users"][0]["id"] == user2_id

def test_admin_get_user_360(users_admin_client):
    """Admin retrieves full 360° customer profile with financial and activity feeds."""
    client, user1_id, _ = users_admin_client

    res = client.get(f"/api/admin/users/{user1_id}")
    assert res.status_code == 200
    data = res.json()

    # Profile & Settings
    assert data["profile"]["email"] == "alice@example.com"
    assert data["profile"]["first_name"] == "Alice"
    assert data["profile"]["phone_number"] == "254711111111"

    # Financial & Locks
    assert data["wallet"]["balance"] == 10000
    assert data["wallet"]["is_budget_locked"] is True

    # Feeds
    assert len(data["deposits"]) == 1
    assert data["deposits"][0]["checkout_request_id"] == "chk_alice_1"
    assert len(data["payouts"]) == 1
    assert data["payouts"][0]["amount"] == 500
    assert data["active_sessions_count"] == 1

def test_admin_unlock_user_account(users_admin_client):
    """Admin unlocks a locked customer account and resets failed attempts."""
    client, _, user2_id = users_admin_client

    # Verify initial locked state
    res_user = client.get(f"/api/admin/users/{user2_id}")
    assert res_user.json()["profile"]["failed_login_attempts"] >= 5

    # Unlock user
    res_unlock = client.post(f"/api/admin/users/{user2_id}/unlock", json={
        "reason": "Customer verified identity via phone call"
    })
    assert res_unlock.status_code == 200
    assert res_unlock.json()["status"] == "success"

    # Verify unlocked in 360 view
    res_after = client.get(f"/api/admin/users/{user2_id}")
    assert res_after.json()["profile"]["failed_login_attempts"] == 0

def test_admin_toggle_user_2fa(users_admin_client):
    """Admin can enable or disable 2FA for a user."""
    client, user1_id, _ = users_admin_client

    res = client.post(f"/api/admin/users/{user1_id}/toggle-2fa", json={
        "enabled": True,
        "reason": "Security requirement upgrade"
    })
    assert res.status_code == 200
    assert res.json()["two_factor_enabled"] is True

    # Verify updated
    res_360 = client.get(f"/api/admin/users/{user1_id}")
    assert res_360.json()["profile"]["two_factor_enabled"] is True

def test_admin_revoke_all_user_sessions(users_admin_client):
    """Admin can invalidate all active sessions for a customer."""
    client, user1_id, _ = users_admin_client

    # Check active sessions before
    assert client.get(f"/api/admin/users/{user1_id}").json()["active_sessions_count"] == 1

    # Revoke sessions
    res_revoke = client.post(f"/api/admin/users/{user1_id}/revoke-sessions", json={
        "reason": "Suspicious login detected"
    })
    assert res_revoke.status_code == 200

    # Check active sessions after
    assert client.get(f"/api/admin/users/{user1_id}").json()["active_sessions_count"] == 0

def test_admin_support_impersonation(users_admin_client):
    """Support agent can generate a scoped impersonation session."""
    client, user1_id, _ = users_admin_client

    res_imp = client.post(f"/api/admin/users/{user1_id}/impersonate", json={
        "reason": "Troubleshooting missing disbursement notification"
    })
    assert res_imp.status_code == 200
    data = res_imp.json()
    assert data["status"] == "success"
    assert "impersonation_token" in data
    assert "dashboard" in data["redirect_url"]

def test_admin_update_payout_phone(users_admin_client):
    """Admin can correct a customer's payout phone number."""
    client, user1_id, _ = users_admin_client

    res_update = client.post(f"/api/admin/users/{user1_id}/update-payout-phone", json={
        "phone_number": "254799887766",
        "reason": "Customer lost previous SIM card"
    })
    assert res_update.status_code == 200
    assert res_update.json()["phone_number"] == "254799887766"

    # Verify updated in 360 profile
    res_360 = client.get(f"/api/admin/users/{user1_id}")
    assert res_360.json()["profile"]["phone_number"] == "254799887766"

def test_auditor_role_forbidden_from_support_mutations(users_admin_client):
    """Auditor has read-only access and is forbidden from user mutation actions."""
    client, user1_id, _ = users_admin_client

    # Switch to auditor
    client.post("/api/admin/auth/logout")
    login_aud = client.post("/api/admin/auth/login", json={
        "email": "auditor@bursar.co.ke",
        "password": "Auditor!Pass2026"
    })
    assert login_aud.status_code == 200

    # Auditor CAN view users
    assert client.get("/api/admin/users").status_code == 200
    assert client.get(f"/api/admin/users/{user1_id}").status_code == 200

    # Auditor CANNOT mutate users (403 Forbidden)
    assert client.post(f"/api/admin/users/{user1_id}/unlock", json={"reason": "test"}).status_code == 403
    assert client.post(f"/api/admin/users/{user1_id}/toggle-2fa", json={"enabled": True, "reason": "test"}).status_code == 403
    assert client.post(f"/api/admin/users/{user1_id}/revoke-sessions", json={"reason": "test"}).status_code == 403
    assert client.post(f"/api/admin/users/{user1_id}/impersonate", json={"reason": "test"}).status_code == 403
    assert client.post(f"/api/admin/users/{user1_id}/update-payout-phone", json={"phone_number": "254799887766", "reason": "test"}).status_code == 403
