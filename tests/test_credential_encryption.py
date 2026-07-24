import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db, get_current_user_id
from app.db.manager import DatabaseManager
from app.db.models import Settings
from app.core.encryption import encrypt_credential, decrypt_credential

TEST_DB_FILE = "test_encryption.db"

@pytest.fixture
def test_db():
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass

    manager = DatabaseManager(TEST_DB_FILE)
    manager.initialize()
    yield manager
    manager.close()

    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


def _db_override(manager):
    def override():
        yield manager
    return override


def test_fernet_encryption_decryption_helpers():
    """Test encrypt_credential and decrypt_credential round-trip and edge cases."""
    secret = "my_super_secret_mpesa_key_123"
    encrypted = encrypt_credential(secret)
    
    assert encrypted != secret
    assert encrypted.startswith("enc:")
    
    decrypted = decrypt_credential(encrypted)
    assert decrypted == secret

    # Edge cases
    assert encrypt_credential("") == ""
    assert decrypt_credential("") == ""
    assert encrypt_credential(None) is None
    assert decrypt_credential(None) is None


def test_database_credential_encryption_at_rest(test_db):
    """
    Verifies that when update_settings is called with plaintext mpesa_consumer_secret or
    mpesa_initiator_password, the underlying database row stores enc:... ciphertext.
    """
    user_id = test_db.create_user("254711223344", "pinpassword")
    
    plain_secret = "secret_key_abc_123"
    plain_password = "initiator_password_xyz_456"

    test_db.update_settings(
        user_id,
        mpesa_consumer_secret=plain_secret,
        mpesa_initiator_password=plain_password
    )

    # 1. Query raw ORM row directly from DB session
    raw_settings = test_db.session.query(Settings).filter(Settings.user_id == user_id).first()
    assert raw_settings is not None

    # CRITICAL SECURITY ASSERTIONS: Must be stored encrypted in database!
    assert raw_settings.mpesa_consumer_secret != plain_secret
    assert raw_settings.mpesa_consumer_secret.startswith("enc:")
    assert raw_settings.mpesa_initiator_password != plain_password
    assert raw_settings.mpesa_initiator_password.startswith("enc:")

    # 2. Query via manager get_settings with decrypt_secrets=True (for background payment processing)
    decrypted_settings = test_db.get_settings(user_id, decrypt_secrets=True)
    assert decrypted_settings["mpesa_consumer_secret"] == plain_secret
    assert decrypted_settings["mpesa_initiator_password"] == plain_password


def test_legacy_unencrypted_credentials_fallback(test_db):
    """Verifies that legacy unencrypted plaintext credentials in database decrypt gracefully."""
    user_id = test_db.create_user("254711223355", "pinpassword")
    
    # Fetch existing Settings row created by create_user and write unencrypted raw string
    raw_settings = test_db.session.query(Settings).filter(Settings.user_id == user_id).first()
    raw_settings.mpesa_consumer_secret = "legacy_unencrypted_secret"
    raw_settings.mpesa_initiator_password = "legacy_unencrypted_password"
    test_db.session.commit()

    decrypted = test_db.get_settings(user_id, decrypt_secrets=True)
    assert decrypted["mpesa_consumer_secret"] == "legacy_unencrypted_secret"
    assert decrypted["mpesa_initiator_password"] == "legacy_unencrypted_password"


def test_post_settings_masks_secrets_in_response(test_db):
    """Verifies POST /api/settings returns masked ******** values (Fix for Issue H-02)."""
    user_id = test_db.create_user("254711223366", "pinpassword")
    
    app.dependency_overrides[get_db] = _db_override(test_db)
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        client = TestClient(app)
        payload = {
            "mpesa_consumer_key": "key_123",
            "mpesa_consumer_secret": "my_top_secret_key",
            "mpesa_initiator_password": "my_initiator_password"
        }

        res = client.post("/api/settings", json=payload)
        assert res.status_code == 200
        data = res.json()

        # Issue H-02 Fix Assertion: Response JSON MUST be masked!
        assert data["settings"]["mpesa_consumer_secret"] == "********"
        assert data["settings"]["mpesa_initiator_password"] == "********"

        # GET /api/settings should also be masked
        res_get = client.get("/api/settings")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["mpesa_consumer_secret"] == "********"
        assert data_get["mpesa_initiator_password"] == "********"

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_id, None)


def test_post_settings_preserving_masked_secrets(test_db):
    """Verifies that sending ******** in POST payload preserves existing encrypted credentials in DB."""
    user_id = test_db.create_user("254711223377", "pinpassword")
    
    plain_secret = "original_secret_123"
    test_db.update_settings(user_id, mpesa_consumer_secret=plain_secret)

    app.dependency_overrides[get_db] = _db_override(test_db)
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    try:
        client = TestClient(app)
        # User updates daily_budget while sending masked secret back
        payload = {
            "daily_budget": 500.0,
            "mpesa_consumer_secret": "********"
        }

        res = client.post("/api/settings", json=payload)
        assert res.status_code == 200

        # Original secret should be preserved in DB when decrypted for payment service
        settings = test_db.get_settings(user_id, decrypt_secrets=True)
        assert settings["mpesa_consumer_secret"] == plain_secret

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_id, None)
