import re
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_admin_user, require_admin_roles
from app.core.limiter import limiter
from app.core.config import SESSION_COOKIE_SECURE
from app.api.schemas import (
    AdminUserUnlockPayload,
    AdminUser2FATogglePayload,
    AdminUserRevokeSessionsPayload,
    AdminUserImpersonatePayload,
    AdminUserUpdatePayoutPhonePayload
)

logger = logging.getLogger("bursar.admin.users")

router = APIRouter(prefix="/api/admin/users", tags=["Admin Users"])

PHONE_REGEX = r"^(?:254|\+254|0)?([71](?:(?:[0-9][0-9])|(?:0[0-8]))[0-9]{6})$"

@router.get("")
@limiter.limit("60/minute")
def list_admin_users(
    request: Request,
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    admin: dict = Depends(get_current_admin_user),
    db: DatabaseManager = Depends(get_db)
):
    """Search and paginate customer directory with financial health indicators."""
    users, total = db.get_admin_users_list(
        page=page,
        limit=limit,
        search=search,
        status_filter=status_filter,
        sort_by=sort_by,
        order=order
    )
    return {
        "users": users,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/{user_id}")
@limiter.limit("60/minute")
def get_user_360(
    request: Request,
    user_id: int,
    admin: dict = Depends(get_current_admin_user),
    db: DatabaseManager = Depends(get_db)
):
    """Retrieve full 360° customer profile, wallet, locks, and activity history."""
    data = db.get_user_360(user_id)
    if not data:
        raise HTTPException(status_code=404, detail="Customer account not found")
    return data

@router.post("/{user_id}/unlock")
def unlock_user_account(
    request: Request,
    user_id: int,
    payload: AdminUserUnlockPayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "support"])),
    db: DatabaseManager = Depends(get_db)
):
    """Unlock customer account and reset failed login attempt counter."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    success = db.admin_unlock_user(
        user_id=user_id,
        admin_id=admin["id"],
        reason=payload.reason or "Admin manual account unlock",
        ip_address=ip_address
    )
    if not success:
        raise HTTPException(status_code=404, detail="Customer account not found")
    return {"status": "success", "message": "Customer account unlocked successfully."}

@router.post("/{user_id}/toggle-2fa")
def toggle_user_2fa(
    request: Request,
    user_id: int,
    payload: AdminUser2FATogglePayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "support"])),
    db: DatabaseManager = Depends(get_db)
):
    """Enable or disable two-factor authentication requirement for customer."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    success = db.admin_toggle_user_2fa(
        user_id=user_id,
        enabled=payload.enabled,
        admin_id=admin["id"],
        reason=payload.reason or "Admin 2FA modification",
        ip_address=ip_address
    )
    if not success:
        raise HTTPException(status_code=404, detail="Customer account not found")
    return {"status": "success", "two_factor_enabled": payload.enabled}

@router.post("/{user_id}/revoke-sessions")
def revoke_user_sessions(
    request: Request,
    user_id: int,
    payload: AdminUserRevokeSessionsPayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "support"])),
    db: DatabaseManager = Depends(get_db)
):
    """Revoke all active browser sessions for customer."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    count = db.admin_revoke_all_user_sessions(
        user_id=user_id,
        admin_id=admin["id"],
        reason=payload.reason or "Admin session revocation",
        ip_address=ip_address
    )
    return {"status": "success", "revoked_count": count, "message": f"Successfully revoked {count} active session(s)."}

@router.post("/{user_id}/impersonate")
def impersonate_user(
    request: Request,
    user_id: int,
    payload: AdminUserImpersonatePayload,
    response: Response,
    admin: dict = Depends(require_admin_roles(["superadmin", "support"])),
    db: DatabaseManager = Depends(get_db)
):
    """Issue a scoped temporary customer session for support assistance."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    try:
        token, user_dict = db.admin_impersonate_user(
            user_id=user_id,
            admin_id=admin["id"],
            reason=payload.reason or "Support troubleshooting",
            ip_address=ip_address
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "status": "success",
        "impersonation_token": token,
        "redirect_url": f"/dashboard?impersonated=true&token={token}",
        "user": {
            "id": user_dict["id"],
            "email": user_dict.get("email", ""),
            "phone_number": user_dict.get("phone_number", "")
        }
    }

@router.post("/{user_id}/update-payout-phone")
def update_user_payout_phone(
    request: Request,
    user_id: int,
    payload: AdminUserUpdatePayoutPhonePayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "support"])),
    db: DatabaseManager = Depends(get_db)
):
    """Update payout phone number for customer with mandatory reason audit logging."""
    phone_clean = payload.phone_number.strip().replace(" ", "").replace("-", "")
    match = re.match(PHONE_REGEX, phone_clean)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid Safaricom phone number format. Must be a valid Kenyan mobile number (e.g. 254712345678 or 0712345678)."
        )

    formatted_phone = "254" + match.group(1)
    ip_address = request.client.host if request.client else "127.0.0.1"

    success = db.admin_update_user_payout_phone(
        user_id=user_id,
        phone_number=formatted_phone,
        admin_id=admin["id"],
        reason=payload.reason or "Admin manual phone update",
        ip_address=ip_address
    )
    if not success:
        raise HTTPException(status_code=404, detail="Customer account not found")

    return {
        "status": "success",
        "phone_number": formatted_phone,
        "message": f"Customer payout phone updated to {formatted_phone}."
    }
