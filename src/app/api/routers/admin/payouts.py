import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_admin_user, require_admin_roles
from app.core.limiter import limiter
from app.api.schemas import (
    AdminPayoutRetryPayload,
    AdminPayoutMarkSettledPayload
)
from app.services.payment_gateway import send_b2c_payout
from app.services.scheduler import process_daily_payouts_batch

logger = logging.getLogger("bursar.admin.payouts")

router = APIRouter(prefix="/api/admin/payouts", tags=["Admin Payouts"])

@router.get("")
@limiter.limit("60/minute")
def list_admin_payouts(
    request: Request,
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    payout_date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    admin: dict = Depends(get_current_admin_user),
    db: DatabaseManager = Depends(get_db)
):
    """Retrieve paginated B2C payouts across all customer schedules."""
    payouts, total, total_disbursed = db.get_admin_payouts_list(
        page=page,
        limit=limit,
        status=status,
        search=search,
        payout_date=payout_date,
        date_from=date_from,
        date_to=date_to
    )
    return {
        "payouts": payouts,
        "total": total,
        "total_disbursed": total_disbursed,
        "page": page,
        "limit": limit
    }

@router.post("/{payout_id}/retry")
async def retry_failed_payout(
    request: Request,
    payout_id: int,
    payload: AdminPayoutRetryPayload = AdminPayoutRetryPayload(),
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Reset a failed payout and re-trigger B2C disbursement immediately."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    try:
        payout_dict = db.admin_retry_failed_payout(
            payout_id=payout_id,
            admin_id=admin["id"],
            reason=payload.reason or "Admin manual payout retry",
            ip_address=ip_address
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not payout_dict:
        raise HTTPException(status_code=404, detail="Payout record not found.")

    # Trigger gateway call
    user_id = payout_dict["user_id"]
    settings = db.get_settings(user_id, decrypt_secrets=True) or {}
    try:
        gw_res = await send_b2c_payout(
            phone_number=payout_dict["phone_number"],
            amount=float(payout_dict["amount"]),
            recipient_name=f"User {user_id}",
            narrative="Daily Budget Disbursement (Retry)",
            user_settings=settings
        )
        tracking_id = gw_res.get("conversation_id") or gw_res.get("tracking_id") or ""
        if tracking_id:
            db.update_payout_status(
                conversation_id=tracking_id,
                status="PENDING",
                transaction_id=""
            )
    except Exception as e:
        logger.warning(f"Immediate retry call to gateway failed, left as PENDING for worker: {e}")

    return {"status": "success", "message": f"Payout {payout_id} reset to PENDING and triggered for processing."}

@router.post("/{payout_id}/mark-settled")
def mark_payout_settled(
    request: Request,
    payout_id: int,
    payload: AdminPayoutMarkSettledPayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Manually reconcile and mark a payout as completed with external transaction ref."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    try:
        res = db.admin_manual_settle_payout(
            payout_id=payout_id,
            transaction_id=payload.transaction_id,
            admin_id=admin["id"],
            reason=payload.reason,
            ip_address=ip_address
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/trigger-daily-batch")
async def trigger_daily_batch(
    request: Request,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Manually execute today's daily payout scheduler batch across all eligible users."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    db.create_admin_audit_log(
        admin_id=admin["id"],
        action="ADMIN_TRIGGER_DAILY_PAYOUT_BATCH",
        target_type="System",
        target_id=0,
        reason="Manual trigger of daily payout batch from Admin portal",
        ip_address=ip_address
    )
    result = await process_daily_payouts_batch(db)
    return {"status": "success", "result": result}
