#!/usr/bin/env python3
"""
scripts/create_admin.py — Admin Account Bootstrapping CLI Utility for Bursar 2.0.

Usage:
    python scripts/create_admin.py --email admin@bursar.co.ke --role superadmin
    python scripts/create_admin.py --email support@bursar.co.ke --role support --password MyPassword123!
    python scripts/create_admin.py --email existing@bursar.co.ke --role superadmin --update-role
"""

import os
import sys
import argparse
import getpass
import re

# Ensure src/ directory is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import app.core.config  # Automatically loads .env and environment properties
from app.db.manager import DatabaseManager
from app.core.password import hash_password_argon2, validate_password_strength

EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
ALLOWED_ROLES = ["superadmin", "finops", "support", "auditor"]

def main():
    parser = argparse.ArgumentParser(
        description="Bursar 2.0 Administrator Bootstrapping CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--password", help="Administrator password (prompted securely if omitted)")
    parser.add_argument("--role", default="superadmin", choices=ALLOWED_ROLES, help="RBAC role (default: superadmin)")
    parser.add_argument("--db-url", help="Database connection URL or path (defaults to DATABASE_URL or bursar.db)")
    parser.add_argument("--update-role", action="store_true", help="Update the role of an existing administrator")
    parser.add_argument("--reset-password", action="store_true", help="Reset the password of an existing administrator")

    args = parser.parse_args()

    email_clean = args.email.strip().lower()
    if not re.match(EMAIL_REGEX, email_clean):
        sys.stderr.write(f"[ERROR] Invalid email address format: '{args.email}'\n")
        sys.exit(1)

    db_path = args.db_url or os.environ.get("DATABASE_URL", "bursar.db")
    db = DatabaseManager(db_path)
    db.initialize()

    existing = db.get_admin_by_email(email_clean)

    # 1. Handle Role Update for Existing Admin
    if args.update_role:
        if not existing:
            sys.stderr.write(f"[ERROR] No admin account found with email '{email_clean}'.\n")
            db.close()
            sys.exit(1)
        db.update_admin_role(existing["id"], args.role)
        db.create_admin_audit_log(
            admin_id=None,
            action="ADMIN_CLI_ROLE_UPDATE",
            target_type="AdminUser",
            target_id=existing["id"],
            before_state=f'{{"role": "{existing.get("role", "")}"}}',
            after_state=f'{{"role": "{args.role}"}}',
            reason="Role updated via CLI create_admin script",
            ip_address="127.0.0.1 (CLI)"
        )
        print(f"[SUCCESS] Admin '{email_clean}' role updated to '{args.role}'.")
        db.close()
        sys.exit(0)

    # 2. Handle Existing Admin Duplicate Check
    if existing and not args.reset_password:
        sys.stderr.write(f"[ERROR] An admin account with email '{email_clean}' already exists. Use --update-role or --reset-password to modify.\n")
        db.close()
        sys.exit(1)

    # 3. Handle Password Input & Validation
    password = args.password
    if not password:
        password = getpass.getpass(f"Enter password for admin '{email_clean}': ")
        confirm_password = getpass.getpass("Confirm password: ")
        if password != confirm_password:
            sys.stderr.write("[ERROR] Passwords do not match.\n")
            db.close()
            sys.exit(1)

    pwd_error = validate_password_strength(password, user_context=email_clean)
    if pwd_error:
        sys.stderr.write(f"[ERROR] Password does not meet security requirements: {pwd_error}\n")
        db.close()
        sys.exit(1)

    pwd_hash = hash_password_argon2(password)

    # 4. Handle Password Reset
    if args.reset_password and existing:
        admin_obj = db.session.query(db.models.AdminUser if hasattr(db, 'models') else DatabaseManager).filter_by(id=existing["id"]).first()
        from app.db.models import AdminUser
        admin = db.session.query(AdminUser).filter(AdminUser.id == existing["id"]).first()
        if admin:
            admin.password_hash = pwd_hash
            admin.failed_login_attempts = 0
            admin.account_locked_until = ""
            db._commit()
            db.create_admin_audit_log(
                admin_id=None,
                action="ADMIN_CLI_PASSWORD_RESET",
                target_type="AdminUser",
                target_id=existing["id"],
                reason="Password reset via CLI create_admin script",
                ip_address="127.0.0.1 (CLI)"
            )
            print(f"[SUCCESS] Password for admin '{email_clean}' has been reset successfully.")
        db.close()
        sys.exit(0)

    # 5. Create New Administrator
    try:
        admin_id = db.create_admin_user(
            email=email_clean,
            password_hash=pwd_hash,
            salt="argon2",
            role=args.role
        )
        db.create_admin_audit_log(
            admin_id=None,
            action="ADMIN_CLI_CREATED",
            target_type="AdminUser",
            target_id=admin_id,
            after_state=f'{{"email": "{email_clean}", "role": "{args.role}"}}',
            reason="Administrator created via CLI create_admin script",
            ip_address="127.0.0.1 (CLI)"
        )
        print(f"[SUCCESS] Administrator '{email_clean}' ({args.role}) successfully created with ID: {admin_id}.")
        db.close()
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"[ERROR] Failed to create administrator: {e}\n")
        db.close()
        sys.exit(1)

if __name__ == "__main__":
    main()
