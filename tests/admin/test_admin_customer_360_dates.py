import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, AdminUser, Session as DbSession
from app.core.password import hash_password_argon2

DB_FILE = "test_admin_c360_dates.db"
test_db = None

def get_test_db():
    global test_db
    if test_db is None:
        test_db = DatabaseManager(DB_FILE)
        test_db.initialize()
    return test_db

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
    db = get_test_db()
    db.session.query(DbSession).delete()
    db.session.query(Settings).delete()
    db.session.query(User).delete()
    db.session.query(AdminUser).delete()
    db._commit()
    yield db
    app.dependency_overrides.pop(get_db, None)

def test_admin_js_contains_schedule_start_date_display():
    """Verify admin.js contains schedule range and start_date rendering."""
    with open("src/app/static/js/admin.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "Schedule Range:" in js
    assert "wallet.start_date" in js
    assert "startLabel" in js

def test_admin_customer_360_endpoint_returns_schedule_dates():
    """Verify admin 360 endpoint returns start_date and end_date in wallet payload."""
    db = get_test_db()

    # 1. Create Admin User
    admin_hash = hash_password_argon2("Admin!Pass2026")
    admin = AdminUser(
        email="support@bursar.co.ke",
        password_hash=admin_hash,
        role="support",
        is_active=True
    )
    db.session.add(admin)
    db._commit()

    # 2. Create Customer User with active schedule
    user_hash = hash_password_argon2("Customer!Pass2026")
    user_id = db.create_user_email(
        email="customer_schedule@example.com",
        password_hash=user_hash,
        salt="argon2",
        phone_number="254712000111",
        payout_phone="254712000111"
    )
    db.update_settings(
        user_id,
        balance=4500,
        daily_budget=500,
        start_date="2026-09-05",
        end_date="2026-09-25",
        budget_locked_until="2026-09-25"
    )
    db._commit()

    # 3. Test Manager method
    c360_data = db.get_user_360(user_id)
    assert c360_data["wallet"]["start_date"] == "2026-09-05"
    assert c360_data["wallet"]["end_date"] == "2026-09-25"
    assert c360_data["wallet"]["balance"] == 4500

    # 4. Test API endpoint
    with TestClient(app) as client:
        # Login as Admin
        login_res = client.post("/api/admin/auth/login", json={
            "email": "support@bursar.co.ke",
            "password": "Admin!Pass2026"
        })
        assert login_res.status_code == 200

        # Fetch Customer 360
        res = client.get(f"/api/admin/users/{user_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["wallet"]["start_date"] == "2026-09-05"
        assert data["wallet"]["end_date"] == "2026-09-25"
        assert data["wallet"]["is_budget_locked"] is True
