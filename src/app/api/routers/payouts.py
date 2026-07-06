import datetime
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.manager import DatabaseManager
from app.db.models import Payout
from app.api.dependencies import get_db, get_current_user_id
from app.services.scheduler import check_and_trigger_payout

router = APIRouter(prefix="/api", tags=["Payouts"])

@router.get("/payouts")
def list_payouts(limit: int = 100, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    return db.get_payouts(user_id, limit=limit)

@router.get("/logs")
def list_logs(limit: int = 100, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    return db.get_logs(user_id, limit=limit)

@router.post("/payout/trigger")
async def trigger_payout_manually(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
    try:
        triggered = await check_and_trigger_payout(db, now, user_id=user_id, raise_exceptions=True)
        return {"triggered": triggered, "reason": None}
    except ValueError as e:
        return {"triggered": False, "reason": str(e)}


class InjectFailedPayload(BaseModel):
    payout_date: Optional[str] = None

@router.post("/payout/inject-failed")
def inject_failed_payout(
    payload: InjectFailedPayload,
    user_id: int = Depends(get_current_user_id),
    db: DatabaseManager = Depends(get_db)
):
    """Test-only endpoint: seed a FAILED payout record so E2E tests can verify the retry UI.
    Disabled in production (requires ALLOW_TEST_ENDPOINTS=1 env var).
    """
    if os.environ.get("ALLOW_TEST_ENDPOINTS", "0") != "1":
        raise HTTPException(status_code=404, detail="Not found")

    settings = db.get_settings(user_id)
    if not settings:
        raise HTTPException(status_code=400, detail="User settings not found")

    payout_date = payload.payout_date or datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=3))
    ).strftime("%Y-%m-%d")
    phone_number = settings.get("phone_number") or "254700000000"
    daily_budget = settings.get("daily_budget") or 100.0

    eat_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
    failed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")

    # Remove any existing record for this date first (idempotent for tests)
    existing = db.get_payout_by_user_date(user_id, payout_date)
    if existing:
        db.session.query(Payout).filter(Payout.id == existing["id"]).delete(synchronize_session=False)
        db._commit()

    payout_id = db.create_payout(
        user_id=user_id,
        payout_date=payout_date,
        amount=daily_budget,
        phone_number=phone_number,
        status="FAILED",
        conversation_id="",
        originator_conversation_id=""
    )
    payout = db.session.query(Payout).filter(Payout.id == payout_id).first()
    if payout:
        payout.error_message = "Injected failure for E2E testing"
        payout.failed_at = failed_ts
        db._commit()
    db.log_event(user_id, "INFO", f"[TEST] Injected FAILED payout record for {payout_date}.")
    return {"payout_id": payout_id, "payout_date": payout_date, "status": "FAILED"}
