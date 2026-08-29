import time
import secrets
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db
from app.api.schemas import AdminLoginPayload
from app.core.config import SESSION_COOKIE_SECURE
from app.core.limiter import limiter

logger = logging.getLogger("bursar.admin.auth")

router = APIRouter(prefix="/api/admin/auth", tags=["Admin Auth"])

@router.post("/login")
@limiter.limit("5/minute")
def admin_login(
    request: Request,
    payload: AdminLoginPayload,
    response: Response,
    db: DatabaseManager = Depends(get_db)
):
    email_clean = payload.email.strip().lower()

    # 1. Check if account is locked due to consecutive failed attempts
    is_locked, remaining_secs = db.is_admin_account_locked(email_clean)
    if is_locked:
        remaining_mins = max(1, (remaining_secs + 59) // 60)
        raise HTTPException(
            status_code=403,
            detail=f"Admin account is locked due to consecutive failed attempts. Please try again in {remaining_mins} minute(s)."
        )

    # 2. Fetch admin user
    admin = db.get_admin_by_email(email_clean)
    if not admin:
        # Constant-time mitigation against email enumeration
        db._verify_password("dummy_password", "$argon2id$v=19$m=65536,t=3,p=4$dummy_hash_for_constant_time")
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # 3. Check if account is active
    if not admin.get("is_active", True):
        raise HTTPException(
            status_code=403,
            detail="Admin account is disabled. Please contact a Super Administrator."
        )

    # 4. Verify password
    is_valid = db._verify_password(payload.password, admin["password_hash"], admin.get("salt", "argon2"))
    if not is_valid:
        attempts, locked = db.record_failed_admin_login(email_clean)
        if locked:
            raise HTTPException(
                status_code=403,
                detail="Admin account is locked for 15 minutes due to 5 consecutive failed login attempts."
            )
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # 5. Reset failed login counter on success
    db.reset_failed_admin_login(email_clean)

    # 6. Create admin session token (24h absolute expiration, 15m inactivity enforced on each request)
    token = f"adm_{secrets.token_urlsafe(32)}"
    expires_at = int(time.time()) + 86400
    user_agent = request.headers.get("user-agent", "Unknown Device")
    ip_address = request.client.host if request.client else "127.0.0.1"

    db.create_admin_session(
        admin_id=admin["id"],
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at
    )

    # 7. Audit log the login
    db.create_admin_audit_log(
        admin_id=admin["id"],
        action="ADMIN_LOGIN",
        target_type="AdminUser",
        target_id=admin["id"],
        reason="Successful administrator authentication",
        ip_address=ip_address
    )

    # 8. Set HTTP-only secure cookie
    response.set_cookie(
        key="admin_session_token",
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=86400,
        path="/"
    )

    return {
        "status": "success",
        "admin": {
            "id": admin["id"],
            "email": admin["email"],
            "role": admin["role"]
        }
    }

@router.post("/logout")
def admin_logout(
    response: Response,
    admin_session_token: Optional[str] = Cookie(None),
    db: DatabaseManager = Depends(get_db)
):
    if admin_session_token:
        db.revoke_admin_session(admin_session_token)

    response.delete_cookie(
        key="admin_session_token",
        path="/",
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        httponly=True
    )
    return {"status": "success"}

@router.get("/me")
def get_current_admin_profile(
    admin_session_token: Optional[str] = Cookie(None),
    db: DatabaseManager = Depends(get_db)
):
    if not admin_session_token:
        raise HTTPException(status_code=401, detail="Admin session required. Please log in.")

    admin_id = db.verify_admin_session(admin_session_token, inactivity_timeout_seconds=900)
    if not admin_id:
        raise HTTPException(status_code=401, detail="Admin session expired or invalid. Please log in again.")

    admin = db.get_admin_by_id(admin_id)
    if not admin or not admin.get("is_active", True):
        raise HTTPException(status_code=401, detail="Admin account is inactive or not found.")

    return {
        "id": admin["id"],
        "email": admin["email"],
        "role": admin["role"],
        "created_at": admin.get("created_at", "")
    }
