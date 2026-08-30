import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_admin_user, require_admin_roles
from app.core.limiter import limiter
from app.api.schemas import (
    AdminBalanceAdjustmentPayload,
    AdminLockOverridePayload
)

logger = logging.getLogger("bursar.admin.finances")

router = APIRouter(prefix="/api/admin/finances", tags=["Admin Finances"])

@router.get("/wallets")
@limiter.limit("60/minute")
def list_admin_wallets(
    request: Request,
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    sort_by: str = "balance",
    order: str = "desc",
    admin: dict = Depends(get_current_admin_user),
    db: DatabaseManager = Depends(get_db)
):
    """Retrieve platform-wide customer wallet balances and liquidity distribution."""
    wallets, total, total_platform_balance = db.get_admin_wallets_list(
        page=page,
        limit=limit,
        search=search,
        sort_by=sort_by,
        order=order
    )
    return {
        "wallets": wallets,
        "total": total,
        "total_platform_balance": total_platform_balance,
        "page": page,
        "limit": limit
    }

@router.post("/adjust-balance")
def adjust_user_balance(
    request: Request,
    payload: AdminBalanceAdjustmentPayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Execute atomic ledger balance adjustment (CREDIT or DEBIT) with mandatory reason."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    try:
        prev_balance, new_balance = db.admin_adjust_user_balance(
            user_id=payload.user_id,
            amount=payload.amount,
            adjustment_type=payload.adjustment_type,
            admin_id=admin["id"],
            reason=payload.reason,
            reference_id=payload.reference_id,
            ip_address=ip_address
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "user_id": payload.user_id,
        "previous_balance": prev_balance,
        "new_balance": new_balance,
        "adjustment": payload.amount,
        "adjustment_type": payload.adjustment_type,
        "message": f"Successfully {payload.adjustment_type.lower()}ed KES {payload.amount:,} to user {payload.user_id}."
    }

@router.post("/{user_id}/override-deposit-lock")
def override_deposit_lock(
    request: Request,
    user_id: int,
    payload: AdminLockOverridePayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Emergency administrative override to release locked customer deposit funds."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    success = db.admin_override_deposit_lock(
        user_id=user_id,
        admin_id=admin["id"],
        reason=payload.reason,
        ip_address=ip_address
    )
    if not success:
        raise HTTPException(status_code=404, detail="Customer account not found")

    return {"status": "success", "message": "Deposit lock removed successfully."}

@router.post("/{user_id}/override-budget-lock")
def override_budget_lock(
    request: Request,
    user_id: int,
    payload: AdminLockOverridePayload,
    admin: dict = Depends(require_admin_roles(["superadmin", "finops"])),
    db: DatabaseManager = Depends(get_db)
):
    """Emergency administrative override to release active customer budget lock."""
    ip_address = request.client.host if request.client else "127.0.0.1"
    success = db.admin_override_budget_lock(
        user_id=user_id,
        admin_id=admin["id"],
        reason=payload.reason,
        ip_address=ip_address
    )
    if not success:
        raise HTTPException(status_code=404, detail="Customer account not found")

    return {"status": "success", "message": "Budget lock removed successfully."}
