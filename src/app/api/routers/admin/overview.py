import datetime
from fastapi import APIRouter, Depends, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_admin_user
from app.core import config
from app.core.limiter import limiter

router = APIRouter(prefix="/api/admin/overview", tags=["Admin Overview"])

@router.get("")
@limiter.limit("30/minute")
def get_admin_overview(
    request: Request,
    admin: dict = Depends(get_current_admin_user),
    db: DatabaseManager = Depends(get_db)
):
    """Retrieve real-time executive telemetry, platform float, and queue metrics."""
    metrics = db.get_admin_overview_metrics()

    # System Health and Diagnostics
    metrics["system"] = {
        "status": "healthy",
        "app_version": config.APP_VERSION,
        "commit_hash": config.COMMIT_HASH,
        "server_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "admin_user": {
            "email": admin.get("email"),
            "role": admin.get("role")
        }
    }

    return metrics
