import pytest
import datetime
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import AdminUser, Deposit, Session as DbSession, User, Wallet
from app.api.dependencies import admin_session_manager

DB_FILE = "test_admin_overview_deposits_today.db"
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
    db.session.query(Deposit).delete()
    db.session.query(DbSession).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db.session.query(AdminUser).delete()
    db.session.commit()
    yield
    db.session.rollback()

def _create_admin_client(role="superadmin"):
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Admin!P@ss2026Secure")
    admin_id = db.create_admin_user(
        email=f"admin_{role}@bursar.co.ke",
        password_hash=pwd_hash,
        salt=salt,
        role=role
    )

    token = admin_session_manager.create_session(admin_id, role=role, db=db)
    client = TestClient(app)
    client.cookies.set("admin_session_token", token)
    return client, admin_id

def test_admin_overview_aggregates_today_deposits_in_eat_timezone_accurately():
    """Verify get_admin_overview_metrics computes today's deposit inflow separately from all-time cumulative deposits."""
    db = get_test_db()
    
    # Create test user
    pwd_hash, salt = db._hash_password("UserPass123!")
    user_id = db.create_user_email("saver@example.com", pwd_hash, salt)

    eat_tz = datetime.timezone(datetime.timedelta(hours=3))
    now_eat = datetime.datetime.now(eat_tz)
    now_utc = now_eat.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    yesterday_utc = (now_eat - datetime.timedelta(days=1)).astimezone(datetime.timezone.utc).replace(tzinfo=None)

    # 1. Deposit from yesterday (KES 3,000 completed)
    d1 = Deposit(
        user_id=user_id,
        checkout_request_id="ws_CO_yesterday_001",
        amount=3000,
        status="COMPLETED",
        created_at=yesterday_utc
    )
    # 2. Deposit from today (KES 1,500 completed)
    d2 = Deposit(
        user_id=user_id,
        checkout_request_id="ws_CO_today_002",
        amount=1500,
        status="COMPLETED",
        created_at=now_utc
    )
    # 3. Deposit from today (KES 500 completed)
    d3 = Deposit(
        user_id=user_id,
        checkout_request_id="ws_CO_today_003",
        amount=500,
        status="SUCCESS",
        created_at=now_utc
    )
    # 4. Deposit from today (KES 2,000 PENDING)
    d4 = Deposit(
        user_id=user_id,
        checkout_request_id="ws_CO_today_004",
        amount=2000,
        status="PENDING",
        created_at=now_utc
    )
    db.session.add_all([d1, d2, d3, d4])
    db.session.commit()

    # Query DB overview metrics directly
    metrics = db.get_admin_overview_metrics()
    
    # All time completed = 3000 + 1500 + 500 = 5000
    assert metrics["float"]["total_deposited_all_time"] == 5000
    
    # Today's completed inflow = 1500 + 500 = 2000
    assert metrics["float"]["today_deposited_amount"] == 2000
    assert metrics["float"]["today_deposited_count"] == 2
    assert metrics["deposit_velocity"]["today_deposited_amount"] == 2000
    assert metrics["deposit_velocity"]["today_deposited_count"] == 2

    # Query via HTTP endpoint
    client, admin_id = _create_admin_client()
    res = client.get("/api/admin/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["float"]["today_deposited_amount"] == 2000
    assert data["float"]["today_deposited_count"] == 2
    assert data["float"]["total_deposited_all_time"] == 5000
