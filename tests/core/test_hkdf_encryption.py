import pytest
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from app.core.encryption import encrypt_credential, decrypt_credential, _get_fernet, _get_legacy_fernet
from app.core.config import SECRET_KEY

def test_hkdf_fernet_key_derivation():
    """Verify Fernet instance uses HKDF-SHA256 derived key for cryptographic domain separation (SEC-008)."""
    f = _get_fernet()
    assert isinstance(f, Fernet)

    # Test encryption and decryption with HKDF key
    plaintext = "super-secret-mpesa-consumer-key-12345"
    encrypted = encrypt_credential(plaintext)
    
    assert encrypted.startswith("enc:")
    assert encrypted != plaintext
    
    decrypted = decrypt_credential(encrypted)
    assert decrypted == plaintext

def test_legacy_fernet_token_backward_compatibility():
    """
    Verify credentials encrypted under the old SHA-256 scheme can still be decrypted
    seamlessly via the backward compatibility fallback path.
    """
    raw_secret = SECRET_KEY.get_secret_value() if hasattr(SECRET_KEY, "get_secret_value") else str(SECRET_KEY)
    legacy_key_bytes = hashlib.sha256(raw_secret.encode('utf-8')).digest()
    legacy_fernet_key = base64.urlsafe_b64encode(legacy_key_bytes)
    legacy_fernet = Fernet(legacy_fernet_key)
    
    plaintext = "legacy-mpesa-initiator-password"
    legacy_ciphertext = f"enc:{legacy_fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')}"
    
    # decrypt_credential should automatically fallback and decrypt legacy ciphertext
    decrypted = decrypt_credential(legacy_ciphertext)
    assert decrypted == plaintext
