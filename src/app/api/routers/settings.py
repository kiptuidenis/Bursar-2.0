import re
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.api.schemas import SettingsUpdate
from app.core.limiter import limiter

router = APIRouter(prefix="/api/settings", tags=["Settings"])

@router.get("")
def get_settings(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    settings = db.get_settings(user_id)
    if not settings:
        return {}
    
    masked = dict(settings)
    for field in ["mpesa_consumer_secret", "mpesa_initiator_password"]:
        if masked.get(field):
            masked[field] = "********"
        else:
            masked[field] = ""
            
    # Add derived lock flags
    is_locked = db.is_budget_locked(user_id)
    masked["is_budget_locked"] = is_locked
    masked["is_deposit_locked"] = db.is_deposit_locked(user_id)
    return masked

@router.post("")
@limiter.limit("10/minute")
def update_settings(request: Request, payload: SettingsUpdate, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No settings provided to update")
        
    current = db.get_settings(user_id)
    
    # Validate start_date and end_date formats and ranges
    if "start_date" in updates and updates["start_date"]:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", updates["start_date"]):
            raise HTTPException(status_code=400, detail="Invalid start date format. Must be YYYY-MM-DD.")
    if "end_date" in updates and updates["end_date"]:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", updates["end_date"]):
            raise HTTPException(status_code=400, detail="Invalid end date format. Must be YYYY-MM-DD.")
            
    start = updates.get("start_date") if "start_date" in updates else (current.get("start_date") if current else "")
    end = updates.get("end_date") if "end_date" in updates else (current.get("end_date") if current else "")
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="End date cannot be earlier than start date.")
    
    # 1. Enforce budget lock on daily_budget updates
    if "daily_budget" in updates:
        new_val = updates["daily_budget"]
        old_val = current.get("daily_budget", 0.0) if current else 0.0
        if new_val != old_val and db.is_budget_locked(user_id):
            raise HTTPException(status_code=400, detail="Daily budget is locked until the end of the month.")
            
        balance = updates.get("balance", current.get("balance", 0.0) if current else 0.0)
        if new_val > balance and balance > 0:
            raise HTTPException(status_code=400, detail=f"Daily budget (KES {new_val:.2f}) cannot be more than your deposit balance (KES {balance:.2f}).")
            
    # 2. Enforce deposit lock on balance updates (reject decreases)
    if "balance" in updates:
        new_bal = updates["balance"]
        old_bal = current.get("balance", 0.0) if current else 0.0
        if new_bal < old_bal and db.is_deposit_locked(user_id):
            raise HTTPException(status_code=400, detail="Deposits are locked and balance cannot be manually decreased until the end of the month.")
            
        daily_budget = updates.get("daily_budget", current.get("daily_budget", 0.0) if current else 0.0)
        if daily_budget > new_bal and new_bal > 0:
            raise HTTPException(status_code=400, detail=f"Deposit balance (KES {new_bal:.2f}) cannot be less than your daily budget (KES {daily_budget:.2f}).")
            
    for field in ["mpesa_consumer_secret", "mpesa_initiator_password"]:
        if updates.get(field) == "********":
            if current and current.get(field):
                updates[field] = current[field]
            else:
                updates[field] = ""
                
    # 3. Validate payout_time format and ensure it is not in the past today if changed
    if "payout_time" in updates and updates["payout_time"]:
        payout_time_str = updates["payout_time"]
        old_payout_time = current.get("payout_time", "") if current else ""
        if payout_time_str != old_payout_time:
            if not re.match(r"^\d{2}:\d{2}$", payout_time_str):
                raise HTTPException(status_code=400, detail="Invalid payout time format. Must be HH:MM.")
            try:
                h, m = map(int, payout_time_str.split(":"))
                if h < 0 or h > 23 or m < 0 or m > 59:
                    raise ValueError()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid hours or minutes in payout time.")
                
            now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
            if h < now.hour or (h == now.hour and m <= now.minute):
                raise HTTPException(status_code=400, detail="Payout time cannot be in the past today. Please choose a future time.")

    db.update_settings(user_id, **updates)
    db.log_event(user_id, "INFO", "Wallet and API configuration updated.")
    
    res = db.get_settings(user_id)
    # Expose derived lock flags in return payload
    res_dict = dict(res) if res else {}
    res_dict["is_budget_locked"] = db.is_budget_locked(user_id)
    res_dict["is_deposit_locked"] = db.is_deposit_locked(user_id)
    return {"status": "success", "settings": res_dict}
