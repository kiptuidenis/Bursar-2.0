import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from app.core.config import SECRET_KEY

_fernet_instance: Optional[Fernet] = None
_legacy_fernet_instance: Optional[Fernet] = None

def _get_raw_secret_bytes() -> bytes:
    raw_secret = SECRET_KEY.get_secret_value() if hasattr(SECRET_KEY, "get_secret_value") else str(SECRET_KEY)
    return raw_secret.encode('utf-8')

def _get_fernet() -> Fernet:
    """
    Derive a dedicated Fernet encryption key from SECRET_KEY using HKDF-SHA256
    with cryptographic domain separation (SEC-008).
    """
    global _fernet_instance
    if _fernet_instance is None:
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"bursar-credential-encryption-v1",
            info=b"mpesa-credential-fernet-key"
        )
        derived_key = hkdf.derive(_get_raw_secret_bytes())
        fernet_key = base64.urlsafe_b64encode(derived_key)
        _fernet_instance = Fernet(fernet_key)
    return _fernet_instance

def _get_legacy_fernet() -> Fernet:
    """Legacy helper: Derive Fernet key using raw SHA-256 for backward compatibility decryption."""
    global _legacy_fernet_instance
    if _legacy_fernet_instance is None:
        key_bytes = hashlib.sha256(_get_raw_secret_bytes()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        _legacy_fernet_instance = Fernet(fernet_key)
    return _legacy_fernet_instance

def encrypt_credential(plain_text: Optional[str]) -> Optional[str]:
    """
    Encrypts a sensitive plaintext credential into ciphertext prefixed with 'enc:' using HKDF-derived key.
    If input is None, empty, or already starts with 'enc:', returns as-is.
    """
    if plain_text is None:
        return None
    if not plain_text or plain_text == "********":
        return plain_text
    if plain_text.startswith("enc:"):
        return plain_text

    f = _get_fernet()
    token = f.encrypt(plain_text.encode('utf-8')).decode('utf-8')
    return f"enc:{token}"

def decrypt_credential(cipher_text: Optional[str]) -> Optional[str]:
    """
    Decrypts an 'enc:' prefixed ciphertext credential back to plaintext.
    Tries HKDF-derived key first, falling back to legacy raw SHA-256 key for backward compatibility.
    """
    if cipher_text is None:
        return None
    if not cipher_text or cipher_text == "********":
        return cipher_text
    if not cipher_text.startswith("enc:"):
        # Backwards compatibility: raw unencrypted string
        return cipher_text

    token = cipher_text[4:]  # strip 'enc:' prefix
    try:
        f = _get_fernet()
        return f.decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        try:
            # Fallback for legacy ciphertext encrypted under raw SHA-256 scheme
            legacy_f = _get_legacy_fernet()
            return legacy_f.decrypt(token.encode('utf-8')).decode('utf-8')
        except Exception:
            return cipher_text
    except Exception:
        return cipher_text
