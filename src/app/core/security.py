import hmac
import hashlib
import time
import secrets
from typing import Optional

from typing import Optional, List, Union
from pydantic import SecretStr

class SessionManager:
    def __init__(
        self, 
        secret_key: Optional[Union[str, SecretStr, bytes]] = None,
        fallback_secret_keys: Optional[List[Union[str, SecretStr, bytes]]] = None
    ):
        from app.core.config import parse_secret_key
        if secret_key is not None:
            self.primary_key_bytes = parse_secret_key(secret_key)
        else:
            self.primary_key_bytes = secrets.token_bytes(32)

        self.all_keys_bytes: List[bytes] = [self.primary_key_bytes]

        if fallback_secret_keys:
            for fk in fallback_secret_keys:
                try:
                    parsed_fk = parse_secret_key(fk)
                    if parsed_fk not in self.all_keys_bytes:
                        self.all_keys_bytes.append(parsed_fk)
                except ValueError:
                    continue

    def create_session(self, user_id: int, expires_in_seconds: int = 3600, db = None, user_agent: str = "", ip_address: str = "") -> str:
        """Create a cryptographically signed session token for a user using the primary key."""
        expiration = time.time() + expires_in_seconds
        session_payload = f"{user_id}:{expiration}"
        
        # Calculate HMAC SHA-256 signature using primary key bytes
        signature = hmac.new(
            self.primary_key_bytes,
            session_payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        # Format token: payload + signature
        token = f"{session_payload}:{signature}"
        
        if db is not None:
            db.create_session_db(user_id, token, user_agent, ip_address, int(expiration))
            
        return token

    def validate_session(self, token: Optional[str], db = None, is_poll: bool = False) -> Optional[int]:
        """Verify the signature across primary and fallback keys, and check expiration."""
        if not token:
            return None
            
        parts = token.split(":")
        if len(parts) != 3:
            return None
            
        user_id_str, expiration_str, signature = parts
        session_payload = f"{user_id_str}:{expiration_str}"
        payload_bytes = session_payload.encode("utf-8")

        # Verify signature using constant-time comparison against primary key and fallback keys
        signature_valid = False
        for k_bytes in self.all_keys_bytes:
            expected_signature = hmac.new(
                k_bytes,
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            if hmac.compare_digest(signature, expected_signature):
                signature_valid = True
                break
        
        if not signature_valid:
            return None

            
        # Verify expiration
        try:
            expiration = int(float(expiration_str))
        except ValueError:
            return None
            
        if time.time() > expiration:
            return None
            
        if db is not None:
            db_user_id = db.verify_session_token_db(token, is_poll=is_poll)
            if db_user_id is None:
                return None
            return db_user_id
            
        try:
            return int(user_id_str)
        except ValueError:
            return None
