from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from app.core import config

def get_account_or_ip_key(request: Request) -> str:
    """
    Derives a composite rate-limiting key for per-account / per-session protection (SEC-007).
    Prioritizes authenticated user identifier / session token, falling back to client IP address.
    """
    # 1. Authenticated user ID attached to request state (if set by auth dependency)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    
    # 2. Session cookie token if present
    session_token = request.cookies.get("session_token")
    if session_token:
        return f"session:{session_token}"
        
    # 3. Fallback to client IP address
    return get_remote_address(request)

# Explicitly configure Sliding/Moving Window Counter algorithm for smooth rate calculation
limiter = Limiter(
    key_func=get_account_or_ip_key,
    strategy="moving-window",
    enabled=not config.IS_TEST_MODE,
    default_limits=["120/minute"]
)
