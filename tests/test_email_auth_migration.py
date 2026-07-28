import pytest
import os
from app.db.manager import DatabaseManager
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_email_auth.db")
    db = DatabaseManager(db_file)
    db.initialize()
    yield db
    db.close()
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass

def test_email_user_creation_and_lookup(test_db):
    email = "testuser@example.com"
    password = "ComplexP@ssw0rd99!"
    
    # Create email user
    user_id = test_db.create_user(email, password, is_email=True)
    assert user_id > 0
    
    # Lookup by email
    u = test_db.get_user_by_email("TESTUSER@example.com") # Should handle case-insensitive lookup
    assert u is not None
    assert u["id"] == user_id
    assert u["email"] == "testuser@example.com"
    assert u["phone_number"] is None
    assert u["is_email_verified"] is False
    
    # Authenticate user
    authenticated_id = test_db.authenticate_user("testuser@example.com", password)
    assert authenticated_id == user_id
    
    # Invalid password fails
    assert test_db.authenticate_user("testuser@example.com", "WrongPassword!") is None

def test_legacy_phone_user_creation_and_lookup(test_db):
    phone = "254712345678"
    password = "ComplexP@ssw0rd99!"
    
    # Create legacy phone user
    user_id = test_db.create_user(phone, password, is_email=False)
    assert user_id > 0
    
    # Lookup by phone
    u = test_db.get_user_by_phone(phone)
    assert u is not None
    assert u["id"] == user_id
    assert u["phone_number"] == phone
    assert u["email"] is None
    
    # Authenticate phone user
    authenticated_id = test_db.authenticate_user(phone, password)
    assert authenticated_id == user_id

from app.api.dependencies import get_db

def test_email_auth_api_endpoints(test_db):
    app.dependency_overrides[get_db] = lambda: test_db
    try:
        client = TestClient(app)
        
        # 1. Signup with Email
        email = "api_user@bursar.test"
        password = "ComplexP@ssw0rd99!"
        
        res = client.post("/api/auth/signup", json={
            "email": email,
            "password": password
        })
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert "user_id" in data
        
        # Duplicate email signup fails
        res_dup = client.post("/api/auth/signup", json={
            "email": email,
            "password": password
        })
        assert res_dup.status_code == 400
        assert "already registered" in res_dup.json()["detail"]
        
        # 2. Login with Email
        res_login = client.post("/api/auth/login", json={
            "identifier": email,
            "password": password
        })
        assert res_login.status_code == 200
        assert "session_token" in res_login.cookies
        
        # 3. Check /me endpoint
        res_me = client.get("/api/auth/me", cookies=res_login.cookies)
        assert res_me.status_code == 200
        me_data = res_me.json()
        assert me_data["email"] == email
        assert me_data["is_email_verified"] is False
    finally:
        app.dependency_overrides.clear()

def test_invalid_email_format_rejected(test_db):
    app.dependency_overrides[get_db] = lambda: test_db
    try:
        client = TestClient(app)
        res = client.post("/api/auth/signup", json={
            "email": "not-an-email",
            "password": "ComplexP@ssw0rd99!"
        })
        assert res.status_code == 400
        assert "Invalid email address format" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()

def test_legacy_sqlite_not_null_migration(tmp_path):
    import sqlite3
    db_file = str(tmp_path / "legacy_not_null.db")
    # Manually create a legacy SQLite users table with phone_number NOT NULL
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            salt VARCHAR(255) NOT NULL,
            created_at DATETIME
        );
    """)
    conn.commit()
    conn.close()

    # Now initialize DatabaseManager on this legacy file
    db = DatabaseManager(db_file)
    db.initialize()

    # Creating user via email should now work cleanly without NOT NULL constraint failure
    user_id = db.create_user("legacy_migrated@bursar.test", "ComplexP@ssw0rd99!", is_email=True)
    assert user_id > 0
    u = db.get_user_by_email("legacy_migrated@bursar.test")
    assert u is not None
    db.close()
