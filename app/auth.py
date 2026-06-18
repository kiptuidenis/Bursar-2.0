import hmac
import hashlib
import time
import secrets
from typing import Optional

class SessionManager:
    def __init__(self, secret_key: Optional[str] = None):
        # Generate a random 32-byte hexadecimal key if none is provided
        self.secret_key = secret_key if secret_key is not None else secrets.token_hex(32)

    def create_session(self, user_id: int, expires_in_seconds: int = 3600) -> str:
        """Create a cryptographically signed session token for a user."""
        expiration = int(time.time() + expires_in_seconds)
        session_payload = f"{user_id}:{expiration}"
        
        # Calculate HMAC SHA-256 signature
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            session_payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        # Format token: payload + signature
        return f"{session_payload}:{signature}"

    def validate_session(self, token: Optional[str]) -> Optional[int]:
        """Verify the signature and expiration of a session token. Returns user_id if valid."""
        if not token:
            return None
            
        parts = token.split(":")
        if len(parts) != 3:
            return None
            
        user_id_str, expiration_str, signature = parts
        
        # Verify signature
        session_payload = f"{user_id_str}:{expiration_str}"
        expected_signature = hmac.new(
            self.secret_key.encode("utf-8"),
            session_payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return None
            
        # Verify expiration
        try:
            expiration = int(expiration_str)
        except ValueError:
            return None
            
        if time.time() > expiration:
            return None
            
        try:
            return int(user_id_str)
        except ValueError:
            return None
