import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Session as DbSession
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_profile_input_preservation.db"
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
    db._commit()
    yield db
    app.dependency_overrides.pop(get_db, None)

def test_app_js_guards_profile_inputs_from_polling_clobber():
    """Verify that app.js includes activeElement and dirty checks in fetchProfile."""
    js_path = Path("src/app/static/js/app.js")
    assert js_path.exists(), "app.js does not exist"
    content = js_path.read_text(encoding="utf-8")

    # Verify input preservation logic
    assert "updateField" in content
    assert "document.activeElement !== el" in content
    assert 'el.dataset.dirty !== "true"' in content
    assert "setupProfileHandlers" in content
    assert 'inputEl.dataset.dirty = "true"' in content

def test_profile_api_update_and_retrieval():
    """Verify backend /api/profile handles first_name, last_name, email, and bio updates cleanly."""
    db = get_test_db()
    pwd_hash, salt = db._hash_password("Str0ng!P@ss2026")
    user_id = db.create_user_email(
        email="profile_test@example.com",
        password_hash=pwd_hash,
        salt=salt,
        phone_number="254712345678",
        payout_phone="254712345678"
    )
    user = db.session.query(User).filter(User.id == user_id).first()
    user.email_verified = True
    db._commit()

    c = TestClient(app)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}

    # Update profile
    payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "profile_test@example.com",
        "bio": "Saving for college education."
    }
    res = c.post("/api/profile", json=payload)
    assert res.status_code == 200

    # Get profile
    get_res = c.get("/api/profile")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["first_name"] == "Alice"
    assert data["last_name"] == "Smith"
    assert data["email"] == "profile_test@example.com"
    assert data["bio"] == "Saving for college education."
