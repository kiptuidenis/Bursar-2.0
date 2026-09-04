import os
import time
import datetime
import pytest
from app.db.manager import DatabaseManager
from app.db.models import Base, AdminUser, AdminSession, AdminAuditLog

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_admin.db")
    db = DatabaseManager(db_file)
    db.initialize()
    yield db
    db.close()

def test_admin_user_creation_and_retrieval(test_db):
    """Verify creating and fetching an AdminUser record."""
    admin_id = test_db.create_admin_user(
        email="superadmin@bursar.co.ke",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
        salt="argon2",
        role="superadmin"
    )
    assert admin_id is not None
    assert admin_id > 0

    # Fetch by email
    admin = test_db.get_admin_by_email("superadmin@bursar.co.ke")
    assert admin is not None
    assert admin["id"] == admin_id
    assert admin["email"] == "superadmin@bursar.co.ke"
    assert admin["role"] == "superadmin"
    assert admin["is_active"] is True
    assert admin["failed_login_attempts"] == 0
    assert admin["account_locked_until"] == ""

    # Fetch by id
    admin_by_id = test_db.get_admin_by_id(admin_id)
    assert admin_by_id is not None
    assert admin_by_id["email"] == "superadmin@bursar.co.ke"

def test_duplicate_admin_email_raises_error(test_db):
    """Verify duplicate admin emails are rejected."""
    test_db.create_admin_user(
        email="ops@bursar.co.ke",
        password_hash="hash1",
        salt="argon2",
        role="finops"
    )
    with pytest.raises(ValueError, match="already exists"):
        test_db.create_admin_user(
            email="ops@bursar.co.ke",
            password_hash="hash2",
            salt="argon2",
            role="finops"
        )

def test_admin_session_lifecycle(test_db):
    """Verify admin session creation, verification with inactivity timeout, and revocation."""
    admin_id = test_db.create_admin_user(
        email="support@bursar.co.ke",
        password_hash="hash",
        salt="argon2",
        role="support"
    )
    token = "admin_sec_tok_1234567890abcdef"
    now = int(time.time())
    expires_at = now + 3600

    test_db.create_admin_session(
        admin_id=admin_id,
        token=token,
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        expires_at=expires_at
    )

    # Valid session lookup
    verified_admin_id = test_db.verify_admin_session(token, inactivity_timeout_seconds=900)
    assert verified_admin_id == admin_id

    # Inactivity timeout rejection
    session_obj = test_db.session.query(AdminSession).filter(AdminSession.session_token == token).first()
    assert session_obj is not None
    session_obj.last_activity = now - 950  # 950 seconds ago (> 900s timeout)
    test_db._commit()

    expired_admin_id = test_db.verify_admin_session(token, inactivity_timeout_seconds=900)
    assert expired_admin_id is None

    # Revoked session check
    test_db.create_admin_session(
        admin_id=admin_id,
        token="token_to_revoke",
        ip_address="127.0.0.1",
        user_agent="TestAgent",
        expires_at=now + 3600
    )
    assert test_db.verify_admin_session("token_to_revoke") == admin_id
    revoked = test_db.revoke_admin_session("token_to_revoke")
    assert revoked is True
    assert test_db.verify_admin_session("token_to_revoke") is None

def test_admin_audit_log_creation_and_query(test_db):
    """Verify creating and retrieving immutable admin audit log entries."""
    admin_id = test_db.create_admin_user(
        email="auditor@bursar.co.ke",
        password_hash="hash",
        salt="argon2",
        role="auditor"
    )

    log_id = test_db.create_admin_audit_log(
        admin_id=admin_id,
        action="WALLET_ADJUSTMENT",
        target_type="User",
        target_id=42,
        before_state='{"available_balance": 500}',
        after_state='{"available_balance": 1000}',
        reason="Customer support refund approved by ticket #9021",
        ip_address="192.168.1.50"
    )
    assert log_id is not None
    assert log_id > 0

    logs, total = test_db.get_admin_audit_logs(limit=10, offset=0)
    assert total >= 1
    assert len(logs) >= 1
    entry = logs[0]
    assert entry["admin_id"] == admin_id
    assert entry["action"] == "WALLET_ADJUSTMENT"
    assert entry["target_type"] == "User"
    assert entry["target_id"] == 42
    assert entry["reason"] == "Customer support refund approved by ticket #9021"
    assert entry["ip_address"] == "192.168.1.50"

def test_admin_auto_migration(test_db):
    """Verify that auto-migration ensures admin tables and columns exist cleanly."""
    from sqlalchemy import inspect
    inspector = inspect(test_db.engine)
    assert inspector.has_table("admin_users")
    assert inspector.has_table("admin_sessions")
    assert inspector.has_table("admin_audit_logs")
