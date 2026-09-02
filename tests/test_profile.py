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

from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

def _create_authenticated_client(phone_number, password, email=None, user_agent="Unknown Device"):
    c = TestClient(app, headers={"User-Agent": user_agent})
    db = get_test_db()
    email_clean = email or f"user_{phone_number}@example.com"
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email_clean, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db, user_agent=user_agent)
    c.cookies.set("session_token", token)
    csrf_token = generate_csrf_token()
    c.cookies.set("csrf_token", csrf_token)
    return c, user_id

def test_profile_endpoints():
    c, user_id = _create_authenticated_client("254711223344", "Str0ng!P@ssw0rd", email="alice.smith@example.com")

    # Get empty profile initially
    res_get = c.get("/api/profile")
    assert res_get.status_code == 200
    data = res_get.json()
    assert data["first_name"] == ""
    assert data["last_name"] == ""
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
    c, user_id = _create_authenticated_client("254755667788", "OldP@ssw0rd!")

    # Change PIN with wrong current PIN
    res_err1 = c.post("/api/profile/password", json={"current_password": "WrongP@ssw0rd!", "new_password": "NewP@ssw0rd!"})
    assert res_err1.status_code == 401

    # Change PIN with too short new PIN
    res_err2 = c.post("/api/profile/password", json={"current_password": "OldP@ssw0rd!", "new_password": "123"})
    assert res_err2.status_code == 400

    # Change PIN to same as current password (should fail with 400)
    res_err_reuse = c.post("/api/profile/password", json={"current_password": "OldP@ssw0rd!", "new_password": "OldP@ssw0rd!"})
    assert res_err_reuse.status_code == 400
    assert "cannot be the same" in res_err_reuse.json()["detail"].lower()

    # Successful PIN change
    res_ok = c.post("/api/profile/password", json={"current_password": "OldP@ssw0rd!", "new_password": "NewP@ssw0rd!"})
    assert res_ok.status_code == 200

    # Verify old login credentials fail
    db = get_test_db()
    user = db.session.query(User).filter(User.id == user_id).first()
    assert not db._verify_password("OldP@ssw0rd!", user.password_hash, user.salt)
    assert db._verify_password("NewP@ssw0rd!", user.password_hash, user.salt)

def test_session_tracking_and_revocation():
    c_a, user_id = _create_authenticated_client("254799001122", "Str0ng!P@ssw0rd", user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/114.0.0.0")

    # Device B session creation
    db = get_test_db()
    token_b = session_manager.create_session(user_id, expires_in_seconds=86400, db=db, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5) Safari/605.1.15")
    c_b = TestClient(app)
    c_b.cookies.set("session_token", token_b)

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

def test_account_deactivation():
    c, user_id = _create_authenticated_client("254700112233", "Str0ng!P@ssw0rd")
    db = get_test_db()
    user = db.session.query(User).filter(User.id == user_id).first()
    otp_code = db.create_otp_challenge(user.email, purpose="account_deactivation", ttl_seconds=300, user_id=user_id)

    # Mismatched confirmation phrase fails
    res_err1 = c.post("/api/profile/deactivate", json={"password": "Str0ng!P@ssw0rd", "confirmation": "DELET", "otp_code": otp_code})
    assert res_err1.status_code == 400

    # Incorrect password fails
    res_err2 = c.post("/api/profile/deactivate", json={"password": "WrongP@ssw0rd!", "confirmation": "DELETE", "otp_code": otp_code})
    assert res_err2.status_code == 401

    # Deactivation with positive balance should fail
    db.adjust_balance(user_id, 500.0)
    res_err_balance = c.post("/api/profile/deactivate", json={"password": "Str0ng!P@ssw0rd", "confirmation": "DELETE", "otp_code": otp_code})
    assert res_err_balance.status_code == 400
    assert "balance" in res_err_balance.json()["detail"].lower()
    
    # Reset balance to 0 and verify deactivation succeeds
    db.adjust_balance(user_id, -500.0)

    # Generate fresh OTP code since previous OTP was consumed
    fresh_otp = db.create_otp_challenge(user.email, purpose="account_deactivation", ttl_seconds=300, user_id=user_id)

    # Successful deactivation
    res_ok = c.post("/api/profile/deactivate", json={"password": "Str0ng!P@ssw0rd", "confirmation": "DELETE", "otp_code": fresh_otp})
    assert res_ok.status_code == 200

    # Verify user is completely removed from DB
    users_post = db.get_all_users()
    assert not any(u["id"] == user_id for u in users_post)

    # Verify subsequent requests are 401
    assert c.get("/api/profile").status_code == 401

def test_avatar_upload():
    c, user_id = _create_authenticated_client("254722334455", "Str0ng!P@ssw0rd")

    # Test file upload with wrong type (e.g. text file)
    txt_file = io.BytesIO(b"Hello avatar text")
    res_err1 = c.post("/api/profile/avatar", files={"file": ("avatar.txt", txt_file, "text/plain")})
    assert res_err1.status_code == 400

    # Test file upload with size limit exceeded (e.g. > 2MB)
    huge_data = b"0" * (2 * 1024 * 1024 + 10)
    huge_file = io.BytesIO(huge_data)
    res_err2 = c.post("/api/profile/avatar", files={"file": ("avatar.png", huge_file, "image/png")})
    assert res_err2.status_code == 400

    # Successful image upload with valid PNG bytes
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buf, format="PNG")
    png_data = buf.getvalue()
    img_file = io.BytesIO(png_data)
    res_ok = c.post("/api/profile/avatar", files={"file": ("avatar.png", img_file, "image/png")})
    assert res_ok.status_code == 200
    assert "avatar_url" in res_ok.json()
    avatar_url = res_ok.json()["avatar_url"]
    assert avatar_url.startswith("/uploads/avatars/")

    # Clean up uploaded test file
    rel_path = avatar_url.lstrip("/")
    filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "app", "static", rel_path)
    if os.path.exists(filepath):
        os.remove(filepath)
    filepath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "app", "static", rel_path)
    if os.path.exists(filepath):
        os.remove(filepath)
