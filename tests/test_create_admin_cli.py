import os
import sys
import subprocess
import pytest
from app.db.manager import DatabaseManager

@pytest.fixture
def cli_test_db(tmp_path):
    db_file = str(tmp_path / "test_cli_admin.db")
    db = DatabaseManager(db_file)
    db.initialize()
    db.close()
    return db_file

def run_create_admin_cli(args: list, db_url: str, input_text: str = None) -> subprocess.CompletedProcess:
    """Helper to execute scripts/create_admin.py subprocess."""
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "create_admin.py"),
        "--db-url", db_url
    ] + args

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        env=env
    )

def test_cli_create_admin_success(cli_test_db):
    """CLI successfully creates a new superadmin account."""
    res = run_create_admin_cli([
        "--email", "cli_admin@bursar.co.ke",
        "--password", "Str0ng!RootPass2026",
        "--role", "superadmin"
    ], db_url=cli_test_db)

    assert res.returncode == 0
    assert "successfully created" in res.stdout.lower()

    # Verify in DB
    db = DatabaseManager(cli_test_db)
    admin = db.get_admin_by_email("cli_admin@bursar.co.ke")
    assert admin is not None
    assert admin["role"] == "superadmin"
    assert admin["is_active"] is True
    db.close()

def test_cli_create_admin_custom_role(cli_test_db):
    """CLI creates an admin with finops role."""
    res = run_create_admin_cli([
        "--email", "finops_cli@bursar.co.ke",
        "--password", "FinOps!Pass2026",
        "--role", "finops"
    ], db_url=cli_test_db)

    assert res.returncode == 0
    assert "successfully created" in res.stdout.lower()

    db = DatabaseManager(cli_test_db)
    admin = db.get_admin_by_email("finops_cli@bursar.co.ke")
    assert admin is not None
    assert admin["role"] == "finops"
    db.close()

def test_cli_create_admin_weak_password_rejected(cli_test_db):
    """CLI rejects weak passwords with exit code 1."""
    res = run_create_admin_cli([
        "--email", "weak@bursar.co.ke",
        "--password", "weak",
        "--role", "support"
    ], db_url=cli_test_db)

    assert res.returncode != 0
    assert "password" in res.stderr.lower() or "password" in res.stdout.lower()

def test_cli_create_admin_duplicate_without_update_fails(cli_test_db):
    """Creating an existing admin without update flag fails."""
    # 1. Create first
    res1 = run_create_admin_cli([
        "--email", "dup@bursar.co.ke",
        "--password", "First!Pass2026",
        "--role", "support"
    ], db_url=cli_test_db)
    assert res1.returncode == 0

    # 2. Duplicate create fails
    res2 = run_create_admin_cli([
        "--email", "dup@bursar.co.ke",
        "--password", "Second!Pass2026",
        "--role", "finops"
    ], db_url=cli_test_db)
    assert res2.returncode != 0
    assert "already exists" in (res2.stderr + res2.stdout).lower()

def test_cli_update_existing_admin_role(cli_test_db):
    """CLI updates role for existing admin when --update-role flag is passed."""
    # 1. Create as support
    run_create_admin_cli([
        "--email", "promoted@bursar.co.ke",
        "--password", "Promote!Pass2026",
        "--role", "support"
    ], db_url=cli_test_db)

    # 2. Update role to superadmin
    res_update = run_create_admin_cli([
        "--email", "promoted@bursar.co.ke",
        "--role", "superadmin",
        "--update-role"
    ], db_url=cli_test_db)

    assert res_update.returncode == 0
    assert "role updated" in res_update.stdout.lower()

    db = DatabaseManager(cli_test_db)
    admin = db.get_admin_by_email("promoted@bursar.co.ke")
    assert admin["role"] == "superadmin"
    db.close()
