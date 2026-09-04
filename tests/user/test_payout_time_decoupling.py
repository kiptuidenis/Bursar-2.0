import pytest
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Session as DbSession, Wallet, Budget
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_payout_time_decoupling.db"
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
    db.session.query(Budget).delete()
    db.session.query(Wallet).delete()
    db.session.query(User).delete()
    db.session.commit()
    yield
    db.session.rollback()
    app.dependency_overrides.pop(get_db, None)
    db.close()

def _create_authenticated_client(phone="254711223344", password="StrongPassword123!"):
    db = get_test_db()
    user_id = db.create_user(phone, password)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    client = TestClient(app)
    client.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    client.cookies.set("csrf_token", csrf)
    client.headers = {"X-CSRF-Token": csrf}
    return client, user_id

def test_payout_time_accepts_all_valid_daily_hours():
    """Verify that any valid HH:MM time across the 24-hour day is accepted without clock-time restrictions."""
    client, user_id = _create_authenticated_client()
    db = get_test_db()

    test_times = [
        "00:00",  # Midnight
        "04:15",  # Early morning
        "08:00",  # Morning standard
        "12:00",  # Noon
        "15:45",  # Afternoon
        "20:30",  # Evening
        "23:59",  # End of day
    ]

    for t in test_times:
        res = client.post("/api/settings", json={"payout_time": t})
        assert res.status_code == 200, f"Expected {t} to be accepted, got {res.status_code}: {res.text}"
        assert res.json()["status"] == "success"
        
        # Verify persistence in both database and GET response
        settings = db.get_settings(user_id)
        assert settings["payout_time"] == t

        res_get = client.get("/api/settings")
        assert res_get.status_code == 200
        assert res_get.json()["payout_time"] == t

def test_payout_time_rejects_malformed_and_out_of_bounds_inputs():
    """Verify that malformed or out-of-bounds time strings are strictly rejected with HTTP 400."""
    client, user_id = _create_authenticated_client()

    invalid_times = [
        "24:00",     # Hour 24 out of bounds
        "25:30",     # Hour 25 out of bounds
        "12:60",     # Minute 60 out of bounds
        "08:99",     # Minute 99 out of bounds
        "8:00",      # Missing leading zero
        "08:0",      # Missing minute digit
        "invalid",   # Non-numeric
        "12-30",     # Invalid delimiter
        "12:30:00",  # Too many parts
        "-1:00",     # Negative hour
    ]

    for inv in invalid_times:
        res = client.post("/api/settings", json={"payout_time": inv})
        assert res.status_code == 400, f"Expected {inv} to be rejected with 400, got {res.status_code}"
        assert "payout time" in res.json()["detail"].lower()

def test_schedule_start_date_remains_strictly_future():
    """Verify that start_date strictly requires tomorrow or later regardless of payout_time."""
    client, user_id = _create_authenticated_client()
    import datetime
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).date()
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_str = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_week_str = (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    # Today is rejected
    res_today = client.post("/api/settings", json={"start_date": today_str})
    assert res_today.status_code == 400
    assert "start date must be in the future" in res_today.json()["detail"].lower()

    # Yesterday is rejected
    res_past = client.post("/api/settings", json={"start_date": yesterday_str})
    assert res_past.status_code == 400
    assert "start date must be in the future" in res_past.json()["detail"].lower()

    # Tomorrow with any payout time succeeds
    res_tomorrow = client.post("/api/settings", json={
        "start_date": tomorrow_str,
        "end_date": next_week_str,
        "payout_time": "06:00"
    })
    assert res_tomorrow.status_code == 200
