import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from app.core.config import SECRET_KEY

_fernet_instance: Optional[Fernet] = None

def _get_fernet() -> Fernet:
    """Derive a deterministic Fernet key from SECRET_KEY using SHA-256 digest."""
    global _fernet_instance
    if _fernet_instance is None:
        raw_secret = SECRET_KEY.get_secret_value() if hasattr(SECRET_KEY, "get_secret_value") else str(SECRET_KEY)
        key_bytes = hashlib.sha256(raw_secret.encode('utf-8')).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def encrypt_credential(plain_text: Optional[str]) -> Optional[str]:
    """
    Encrypts a sensitive plaintext credential into ciphertext prefixed with 'enc:'.
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
    If input is None, empty, or unencrypted (legacy data), returns as-is safely.
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
    except Exception:
        # Fallback if decryption fails (e.g. key changed)
        return cipher_text
