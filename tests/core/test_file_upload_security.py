import io
import os
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app, get_db
from app.db.manager import DatabaseManager
from app.db.models import User, Settings, Payout, Log, BudgetItem, Deposit, Session as DbSession

DB_FILE = "test_file_upload_security.db"
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

def create_dummy_png_bytes(width=50, height=50, color=(255, 0, 0)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def create_dummy_jpeg_bytes(width=50, height=50, color=(0, 255, 0)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

from app.api.dependencies import session_manager
from app.core.csrf import generate_csrf_token

def _setup_client(phone_number="254711999111", password="Str0ng!P@ssw0rd"):
    c = TestClient(app)
    db = get_test_db()
    email_clean = f"user_{phone_number}@example.com"
    pwd_hash, salt = db._hash_password(password)
    user_id = db.create_user_email(email_clean, pwd_hash, salt, payout_phone=phone_number, phone_number=phone_number)
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db)
    c.cookies.set("session_token", token)
    csrf = generate_csrf_token()
    c.cookies.set("csrf_token", csrf)
    c.headers = {"X-CSRF-Token": csrf}
    return c, user_id

def test_valid_png_avatar_upload_reencoded():
    client, user_id = _setup_client("254711999111")

    png_bytes = create_dummy_png_bytes()
    response = client.post(
        "/api/profile/avatar",
        files={"file": ("test_avatar.png", png_bytes, "image/png")}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "/uploads/avatars/" in data["avatar_url"]
    assert data["avatar_url"].endswith(".png")

def test_disguised_html_script_rejected():
    client, user_id = _setup_client("254711999222")

    fake_png = b"<script>alert('XSS Vulnerability')</script>"
    response = client.post(
        "/api/profile/avatar",
        files={"file": ("fake_avatar.png", fake_png, "image/png")}
    )

    assert response.status_code == 400
    assert "Invalid or unsupported image file format." in response.json()["detail"]

def test_polyglot_png_reencoded_and_cleaned():
    client, user_id = _setup_client("254711999333")

    # Valid PNG bytes with appended script polyglot payload
    polyglot_bytes = create_dummy_png_bytes() + b"<script>alert('polyglot')</script>"

    response = client.post(
        "/api/profile/avatar",
        files={"file": ("polyglot.png", polyglot_bytes, "image/png")}
    )

    assert response.status_code == 200
    avatar_url = response.json()["avatar_url"]
    
    # Read saved file on disk and verify trailing script tag was stripped by re-encoding
    rel_path = avatar_url.lstrip("/")
    saved_filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "app", "static", rel_path.replace("uploads/", "uploads/"))
    assert os.path.exists(saved_filepath)
    with open(saved_filepath, "rb") as f:
        saved_bytes = f.read()
    assert b"<script>" not in saved_bytes

def test_svg_xml_upload_rejected():
    client, user_id = _setup_client("254711999444")

    svg_payload = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    response = client.post(
        "/api/profile/avatar",
        files={"file": ("image.svg", svg_payload, "image/svg+xml")}
    )

    assert response.status_code == 400
    assert "Invalid or unsupported image file format." in response.json()["detail"]

def test_old_avatar_deleted_on_new_upload():
    client, user_id = _setup_client("254711999555")

    # Upload avatar 1
    res1 = client.post(
        "/api/profile/avatar",
        files={"file": ("avatar1.png", create_dummy_png_bytes(), "image/png")}
    )
    url1 = res1.json()["avatar_url"]
    filename1 = os.path.basename(url1)

    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "app", "static", "uploads", "avatars")
    file1_path = os.path.join(static_dir, filename1)
    assert os.path.exists(file1_path)

    # Upload avatar 2
    res2 = client.post(
        "/api/profile/avatar",
        files={"file": ("avatar2.jpg", create_dummy_jpeg_bytes(), "image/jpeg")}
    )
    url2 = res2.json()["avatar_url"]

    # Verify old file was deleted and new file exists
    assert not os.path.exists(file1_path)
    filename2 = os.path.basename(url2)
    file2_path = os.path.join(static_dir, filename2)
    assert os.path.exists(file2_path)
