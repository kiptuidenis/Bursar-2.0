import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_admin_user, require_admin_roles
from app.api.schemas import AdminStatusTogglePayload
from app.core import config

from sqlalchemy import text

logger = logging.getLogger("bursar.admin.system")

router = APIRouter(prefix="/api/admin/system", tags=["Admin System & Configuration"])

@router.get("/health")
def get_system_health(
    admin: dict = Depends(get_current_admin_user),
    db: DatabaseManager = Depends(get_db)
):
    """Retrieve platform operational health, database connectivity, and gateway modes."""
    # Check DB connectivity
    db_status = "connected"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "environment": config.ENVIRONMENT,
        "scheduler": {
            "running": True,
            "interval_seconds": 60
        },
        "payment_gateway": {
            "mode": config.INTASEND_MODE,
            "provider": "intasend"
        }
    }

@router.get("/admins")
def list_admin_accounts(
    admin: dict = Depends(require_admin_roles(["superadmin"])),
    db: DatabaseManager = Depends(get_db)
):
    """List all staff administrative users (SuperAdmin only)."""
    admins = db.get_admin_users_directory()
    return {"admins": admins, "total": len(admins)}

@router.post("/admins/{admin_id}/toggle-active")
def toggle_admin_active_status(
    request: Request,
    admin_id: int,
    payload: AdminStatusTogglePayload,
    admin: dict = Depends(require_admin_roles(["superadmin"])),
    db: DatabaseManager = Depends(get_db)
):
    """Activate or deactivate staff administrator accounts (SuperAdmin only)."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    try:
        db.admin_toggle_admin_active_status(
            target_admin_id=admin_id,
            is_active=payload.is_active,
            actor_admin_id=admin["id"],
            reason=payload.reason,
            ip_address=ip_address
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "admin_id": admin_id,
        "is_active": payload.is_active,
        "message": f"Administrator account status updated to {'active' if payload.is_active else 'deactivated'}."
    }
