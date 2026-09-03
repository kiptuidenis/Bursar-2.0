import pytest
import datetime
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from fastapi.testclient import TestClient

from app.db.manager import DatabaseManager
from app.db.models import User, Session as DbSession
from app.main import app, get_db
from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

DB_FILE = "test_disclaimer.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
    db = get_test_db()
    db.session.query(DbSession).delete()
    db.session.query(User).delete()
    db._commit()
    yield
    app.dependency_overrides.pop(get_db, None)
    db.close()


def test_user_creation_persists_disclaimer_accepted_and_timestamp():
    """Verify that newly registered users have disclaimer_accepted=True and timestamp linked to their record."""
    db = get_test_db()
    user_id = db.create_user_email(
        email="student_disclaimer@bursar.co.ke",
        password_hash="fakehash",
        salt="argon2"
    )

    user = db.session.query(User).filter(User.id == user_id).first()
    assert user is not None
    assert user.disclaimer_accepted is True
    assert isinstance(user.disclaimer_accepted_at, datetime.datetime)


def test_auth_me_endpoint_returns_disclaimer_accepted_status():
    """Verify that /api/auth/me exposes disclaimer_accepted to the frontend."""
    c = TestClient(app)
    db = get_test_db()
    user_id = db.create_user_email(
        email="auth_me_disclaimer@bursar.co.ke",
        password_hash="fakehash",
        salt="argon2"
    )

    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}

    res = c.get("/api/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["disclaimer_accepted"] is True
    assert data["email"] == "auth_me_disclaimer@bursar.co.ke"
    assert data["disclaimer_accepted_at"] is not None


def test_auto_migration_adds_missing_disclaimer_columns(tmp_path):
    """Verify that _auto_migrate_columns automatically adds disclaimer_accepted columns to legacy users tables."""
    db_path = str(tmp_path / "legacy_users.db")
    engine = create_engine(f"sqlite:///{db_path}")

    # Create legacy table without disclaimer columns
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number VARCHAR(50),
                email VARCHAR(255),
                password_hash VARCHAR(255) NOT NULL,
                salt VARCHAR(255) NOT NULL
            )
        """))

    inspector_before = inspect(engine)
    cols_before = [c["name"] for c in inspector_before.get_columns("users")]
    assert "disclaimer_accepted" not in cols_before
    assert "disclaimer_accepted_at" not in cols_before

    # Run DatabaseManager initialize against legacy DB
    mgr = DatabaseManager(db_path)
    mgr.initialize()

    inspector_after = inspect(mgr.engine)
    cols_after = [c["name"] for c in inspector_after.get_columns("users")]
    assert "disclaimer_accepted" in cols_after
    assert "disclaimer_accepted_at" in cols_after
    mgr.close()


def test_disclaimer_modal_markup_and_css_presence():
    """Verify that index.html, dashboard.html and style.css contain the disclaimer modal components."""
    index_path = Path("src/app/static/index.html")
    assert index_path.exists()
    index_html = index_path.read_text(encoding="utf-8")

    # Assert modal elements in index.html
    assert 'id="disclaimer-overlay"' in index_html
    assert 'id="btn-accept-disclaimer"' in index_html
    assert 'id="btn-decline-disclaimer"' in index_html
    assert "Notice to Users" in index_html
    assert "No Custodial Licenses" in index_html

    # Assert modal elements in dashboard.html
    dash_path = Path("src/app/static/dashboard.html")
    assert dash_path.exists()
    dash_html = dash_path.read_text(encoding="utf-8")
    assert 'id="disclaimer-overlay"' in dash_html
    assert 'id="btn-accept-disclaimer"' in dash_html
    assert 'id="btn-decline-disclaimer"' in dash_html
    assert "Notice to Users" in dash_html

    # Assert CSS rules in style.css
    css_path = Path("src/app/static/css/style.css")
    assert css_path.exists()
    css = css_path.read_text(encoding="utf-8")
    assert ".disclaimer-overlay" in css
    assert ".disclaimer-card" in css
    assert "#btn-accept-disclaimer" in css
    assert "#btn-decline-disclaimer" in css
