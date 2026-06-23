import datetime
from fastapi import APIRouter, Depends, HTTPException
from app.db.manager import DatabaseManager
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
    now = datetime.datetime.now()
    try:
        triggered = await check_and_trigger_payout(db, now, user_id=user_id, raise_exceptions=True)
        return {"triggered": triggered, "reason": None}
    except ValueError as e:
        return {"triggered": False, "reason": str(e)}
