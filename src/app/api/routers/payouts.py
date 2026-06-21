import datetime
from fastapi import APIRouter, Depends, HTTPException
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.services.mpesa import MpesaClient
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
    from app.core.config import (
        MPESA_MODE, MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET,
        MPESA_SHORTCODE, MPESA_INITIATOR_NAME, MPESA_INITIATOR_PASSWORD
    )
    settings = db.get_settings(user_id)
    user_mode = settings.get("mode", "sandbox") if settings else "sandbox"
    client_mode = "simulation" if user_mode == "simulation" else MPESA_MODE
    client = MpesaClient(
        consumer_key=MPESA_CONSUMER_KEY,
        consumer_secret=MPESA_CONSUMER_SECRET,
        shortcode=MPESA_SHORTCODE,
        initiator_name=MPESA_INITIATOR_NAME,
        initiator_password=MPESA_INITIATOR_PASSWORD,
        mode=client_mode
    )
    
    now = datetime.datetime.now()
    triggered = await check_and_trigger_payout(db, client, now, user_id=user_id)
    return {"triggered": triggered}
