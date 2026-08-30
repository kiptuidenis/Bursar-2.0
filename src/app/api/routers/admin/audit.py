import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, require_admin_roles
from app.core.limiter import limiter

logger = logging.getLogger("bursar.admin.audit")

router = APIRouter(prefix="/api/admin/audit", tags=["Admin Audit Logs"])

@router.get("/logs")
@limiter.limit("60/minute")
def list_audit_logs(
    request: Request,
    page: int = 1,
    limit: int = 20,
    action: Optional[str] = None,
    admin_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops", "auditor", "support"])),
    db: DatabaseManager = Depends(get_db)
):
    """Retrieve immutable administrative compliance audit trail."""
    logs, total = db.get_admin_audit_logs_list(
        page=page,
        limit=limit,
        action=action,
        admin_id=admin_id,
        target_type=target_type,
        target_id=target_id,
        date_from=date_from,
        date_to=date_to,
        search=search
    )
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/export")
@limiter.limit("10/minute")
def export_audit_logs_csv(
    request: Request,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops", "auditor", "support"])),
    db: DatabaseManager = Depends(get_db)
):
    """Export compliance audit trail in CSV format for regulatory reporting."""
    csv_data = db.export_admin_audit_logs_csv(
        action=action,
        date_from=date_from,
        date_to=date_to
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=bursar_admin_audit_logs.csv"
        }
    )
