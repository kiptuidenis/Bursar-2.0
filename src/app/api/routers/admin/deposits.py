import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_admin_user, require_admin_roles
from app.core.limiter import limiter
from app.api.schemas import AdminDepositManualSettlePayload
from app.services.payment_gateway import check_stk_status

logger = logging.getLogger("bursar.admin.deposits")

router = APIRouter(prefix="/api/admin/deposits", tags=["Admin Deposits"])

@router.get("")
@limiter.limit("60/minute")
def list_admin_deposits(
    request: Request,
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    admin: dict = Depends(get_current_admin_user),
    db: DatabaseManager = Depends(get_db)
):
    """Retrieve paginated deposit transactions with status and search filters."""
    deposits, total, total_amount = db.get_admin_deposits_list(
        page=page,
        limit=limit,
        status=status,
        search=search,
        date_from=date_from,
        date_to=date_to
    )
    return {
        "deposits": deposits,
        "total": total,
        "total_amount": total_amount,
        "page": page,
        "limit": limit
    }

@router.post("/{checkout_id}/requery")
async def requery_deposit_status(
    request: Request,
    checkout_id: str,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Perform on-demand gateway status query for a stuck deposit transaction."""
    deposit = db.get_deposit(checkout_id)
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit transaction not found.")

    user_id = deposit["user_id"]
    settings = db.get_settings(user_id, decrypt_secrets=False) or {}
    
    try:
        gateway_res = await check_stk_status(checkout_id, settings)
        gw_status = gateway_res.get("status", "PENDING")

        ip_address = request.client.host if request.client else "127.0.0.1"

        if gw_status == "SUCCESS":
            mpesa_rec = gateway_res.get("mpesa_reference") or "GATEWAY_VERIFIED"
            if deposit["status"] != "COMPLETED":
                db.update_deposit_status(checkout_id, "COMPLETED", mpesa_rec)
                db.adjust_balance(user_id, deposit["amount"])
                db.create_admin_audit_log(
                    admin_id=admin["id"],
                    action="ADMIN_DEPOSIT_REQUERY_SETTLE",
                    target_type="Deposit",
                    target_id=deposit["id"],
                    before_state=f'{{"status": "{deposit["status"]}"}}',
                    after_state=f'{{"status": "COMPLETED", "mpesa_receipt": "{mpesa_rec}"}}',
                    reason="Gateway confirmed completed deposit on admin requery",
                    ip_address=ip_address
                )
            return {"status": "COMPLETED", "checkout_request_id": checkout_id, "mpesa_receipt": mpesa_rec, "credited": True}

        elif gw_status == "FAILED":
            if deposit["status"] == "PENDING":
                db.update_deposit_status(checkout_id, "FAILED")
            return {"status": "FAILED", "checkout_request_id": checkout_id}

        return {"status": deposit["status"], "checkout_request_id": checkout_id}

    except Exception as e:
        logger.error(f"Failed to requery deposit status for {checkout_id}: {str(e)}")
        raise HTTPException(status_code=502, detail="Payment gateway query failed.")

@router.post("/{checkout_id}/manual-settle")
def manual_settle_deposit(
    request: Request,
    checkout_id: str,
    payload: AdminDepositManualSettlePayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Manually reconcile and credit a pending deposit with Safaricom M-Pesa receipt."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    try:
        res = db.admin_manual_settle_deposit(
            checkout_request_id=checkout_id,
            mpesa_receipt=payload.mpesa_receipt,
            admin_id=admin["id"],
            reason=payload.reason,
            ip_address=ip_address
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
