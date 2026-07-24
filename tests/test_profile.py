import pytest
import os
import io
import time
from fastapi.testclient import TestClient
from app.db.manager import DatabaseManager
from app.main import app, get_db

DB_FILE = "test_api_profile.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession

@pytest.fixture(autouse=True)
def clean_db():
    app.dependency_overrides[get_db] = get_test_db
    db = get_test_db()
    db.session.query(DbSession).delete()
    db.session.query(BudgetItem).delete()
    db.session.query(Log).delete()
    db.session.query(Deposit).delete()
    db.session.query(Payout).delete()
    db.session.query(Settings).delete()
    db.session.query(User).delete()
    db._commit()
    yield
    app.dependency_overrides.pop(get_db, None)
    db.close()

def test_profile_endpoints():
    c = TestClient(app)
    # Signup
    c.post("/api/auth/signup", json={"phone_number": "254711223344", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254711223344", "password": "pinpassword"})

    # Get empty profile initially
    res_get = c.get("/api/profile")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["first_name"] == ""
    assert data["last_name"] == ""
    assert data["email"] == ""
    assert data["theme"] == ""

    # Update profile
    update_payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice.smith@example.com",
        "bio": "Developer testing money pacing assistant",
        "theme": "light",
        "notifications_enabled": False
    }
    res_post = c.post("/api/profile", json=update_payload)
    assert res_post.status_code == 200
    assert res_post.json()["status"] == "success"
    
    # Verify updates persisted
    res_get2 = c.get("/api/profile")
    data2 = res_get2.json()
    assert data2["first_name"] == "Alice"
    assert data2["last_name"] == "Smith"
    assert data2["email"] == "alice.smith@example.com"
    assert data2["bio"] == "Developer testing money pacing assistant"
    assert data2["theme"] == "light"
    assert data2["notifications_enabled"] is False

    # Invalid email format validation
    res_err = c.post("/api/profile", json={"email": "invalid-email"})
    assert res_err.status_code == 400
    assert "email" in res_err.json()["detail"].lower()

    # Empty/whitespace validation
    res_err_fn = c.post("/api/profile", json={"first_name": ""})
    assert res_err_fn.status_code == 400
    assert "first name" in res_err_fn.json()["detail"].lower()

    res_err_fn_space = c.post("/api/profile", json={"first_name": "   "})
    assert res_err_fn_space.status_code == 400

    res_err_ln = c.post("/api/profile", json={"last_name": ""})
    assert res_err_ln.status_code == 400
    assert "last name" in res_err_ln.json()["detail"].lower()

    res_err_em = c.post("/api/profile", json={"email": ""})
    assert res_err_em.status_code == 400
    assert "email" in res_err_em.json()["detail"].lower()

def test_password_pin_change():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254755667788", "password": "oldpassword"})
    c.post("/api/auth/login", json={"phone_number": "254755667788", "password": "oldpassword"})

    # Change PIN with wrong current PIN
    res_err1 = c.post("/api/profile/password", json={"current_password": "wrongpassword", "new_password": "newpassword"})
    assert res_err1.status_code == 401

    # Change PIN with too short new PIN
    res_err2 = c.post("/api/profile/password", json={"current_password": "oldpassword", "new_password": "123"})
    assert res_err2.status_code == 400

    # Successful PIN change
    res_ok = c.post("/api/profile/password", json={"current_password": "oldpassword", "new_password": "newpassword"})
    assert res_ok.status_code == 200

    # Verify old login details fail
    res_login_old = c.post("/api/auth/login", json={"phone_number": "254755667788", "password": "oldpassword"})
    assert res_login_old.status_code == 401

    # Verify new login details succeed
    c_new = TestClient(app)
    res_login_new = c_new.post("/api/auth/login", json={"phone_number": "254755667788", "password": "newpassword"})
    assert res_login_new.status_code == 200
    assert "session_token" in res_login_new.cookies

def test_session_tracking_and_revocation():
    # Login Device A
    c_a = TestClient(app)
    c_a.post("/api/auth/signup", json={"phone_number": "254799001122", "password": "passwordpin"})
    c_a.post("/api/auth/login", json={"phone_number": "254799001122", "password": "passwordpin"}, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/114.0.0.0"})

    # Login Device B
    c_b = TestClient(app)
    c_b.post("/api/auth/login", json={"phone_number": "254799001122", "password": "passwordpin"}, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5) Safari/605.1.15"})

    # Retrieve sessions via Device A
    res_sessions = c_a.get("/api/profile/sessions")
    assert res_sessions.status_code == 200
    sessions = res_sessions.json()
    assert len(sessions) == 2

    # Verify Device mapping details
    assert "Windows Desktop (Chrome)" in [s["device"] for s in sessions]
    assert "iPhone (Safari)" in [s["device"] for s in sessions]

    # Find Device B session ID
    session_b_id = next(s["id"] for s in sessions if "iPhone" in s["device"])
    session_a_id = next(s["id"] for s in sessions if "Windows" in s["device"])

    # Attempt to self-revoke own session on Device A (should fail with 400)
    res_self_revoke = c_a.delete(f"/api/profile/sessions/{session_a_id}")
    assert res_self_revoke.status_code == 400

    # Revoke Device B session from Device A
    res_revoke = c_a.delete(f"/api/profile/sessions/{session_b_id}")
    assert res_revoke.status_code == 200

    # Verify Device B is now locked out
    res_b_req = c_b.get("/api/profile")
    assert res_b_req.status_code == 401

    # Login Device C
    c_c = TestClient(app)
    c_c.post("/api/auth/login", json={"phone_number": "254799001122", "password": "passwordpin"}, headers={"User-Agent": "Linux; Android Device"})

    # Revoke all other sessions from Device A
    res_revoke_others = c_a.delete("/api/profile/sessions/other")
    assert res_revoke_others.status_code == 200

    # Device C is now locked out
    res_c_req = c_c.get("/api/profile")
    assert res_c_req.status_code == 401

    # Device A remains authenticated
    assert c_a.get("/api/profile").status_code == 200

def test_account_deactivation():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700112233", "password": "passwordpin"})
    c.post("/api/auth/login", json={"phone_number": "254700112233", "password": "passwordpin"})

    db = get_test_db()
    users = db.get_all_users()
    user_id = next(u["id"] for u in users if u["phone_number"] == "254700112233")

    # Mismatched confirmation phrase fails
    res_err1 = c.post("/api/profile/deactivate", json={"password": "passwordpin", "confirmation": "DELET"})
    assert res_err1.status_code == 400

    # Incorrect password fails
    res_err2 = c.post("/api/profile/deactivate", json={"password": "wrongpassword", "confirmation": "DELETE"})
    assert res_err2.status_code == 401

    # Deactivation with positive balance should fail
    db.adjust_balance(user_id, 500.0)
    res_err_balance = c.post("/api/profile/deactivate", json={"password": "passwordpin", "confirmation": "DELETE"})
    assert res_err_balance.status_code == 400
    assert "balance" in res_err_balance.json()["detail"].lower()
    
    # Reset balance to 0 and verify deactivation succeeds
    db.adjust_balance(user_id, -500.0)

    # Successful deactivation
    res_ok = c.post("/api/profile/deactivate", json={"password": "passwordpin", "confirmation": "DELETE"})
    assert res_ok.status_code == 200

    # Verify user is completely removed from DB
    users_post = db.get_all_users()
    assert not any(u["id"] == user_id for u in users_post)

    # Verify subsequent requests are 401
    assert c.get("/api/profile").status_code == 401

def test_avatar_upload():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254722334455", "password": "passwordpin"})
    c.post("/api/auth/login", json={"phone_number": "254722334455", "password": "passwordpin"})

    # Test file upload with wrong type (e.g. text file)
    txt_file = io.BytesIO(b"Hello avatar text")
    res_err1 = c.post("/api/profile/avatar", files={"file": ("avatar.txt", txt_file, "text/plain")})
    assert res_err1.status_code == 400

    # Test file upload with size limit exceeded (e.g. > 2MB)
    huge_data = b"0" * (2 * 1024 * 1024 + 10)
    huge_file = io.BytesIO(huge_data)
    res_err2 = c.post("/api/profile/avatar", files={"file": ("avatar.png", huge_file, "image/png")})
    assert res_err2.status_code == 400

    # Successful image upload
    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..." # Mock minimal PNG
    img_file = io.BytesIO(png_data)
    res_ok = c.post("/api/profile/avatar", files={"file": ("avatar.png", img_file, "image/png")})
    assert res_ok.status_code == 200
    assert "avatar_url" in res_ok.json()
    assert res_ok.json()["avatar_url"].startswith("/uploads/avatars/")

    # Clean up uploaded test file
    db = get_test_db()
    users = db.get_all_users()
    user_id = next(u["id"] for u in users if u["phone_number"] == "254722334455")
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "app", "static", "uploads", "avatars", f"{user_id}_avatar.png")
    if os.path.exists(filepath):
        os.remove(filepath)
