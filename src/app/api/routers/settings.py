import re
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.api.schemas import SettingsUpdate
from app.core.limiter import limiter

router = APIRouter(prefix="/api/settings", tags=["Settings"])

def _mask_sensitive_fields(settings: dict) -> dict:
    masked = dict(settings)
    for field in ["mpesa_consumer_key", "mpesa_consumer_secret", "mpesa_initiator_password"]:
        if masked.get(field):
            masked[field] = "********"
        else:
            masked[field] = ""
    return masked

@router.get("")
@limiter.limit("60/minute")
def get_settings(request: Request, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    settings = db.get_settings(user_id)
    if not settings:
        return {}
    
    masked = _mask_sensitive_fields(settings)
    masked["is_budget_locked"] = db.is_budget_locked(user_id)
    masked["is_deposit_locked"] = db.is_deposit_locked(user_id)
    return masked

@router.post("")
@limiter.limit("10/minute")
def update_settings(request: Request, payload: SettingsUpdate, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No settings provided to update")
        
    current = db.get_settings(user_id)
    
    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d")
    
    # Validate start_date and end_date formats and ranges
    if "start_date" in updates and updates["start_date"]:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", updates["start_date"]):
            raise HTTPException(status_code=400, detail="Invalid start date format. Must be YYYY-MM-DD.")
        if updates["start_date"] <= today_str:
            raise HTTPException(status_code=400, detail="Start date must be in the future (tomorrow or later).")
            
    if "end_date" in updates and updates["end_date"]:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", updates["end_date"]):
            raise HTTPException(status_code=400, detail="Invalid end date format. Must be YYYY-MM-DD.")
            
    start = updates.get("start_date") if "start_date" in updates else (current.get("start_date") if current else "")
    end = updates.get("end_date") if "end_date" in updates else (current.get("end_date") if current else "")
    if start and end and end <= start:
        raise HTTPException(status_code=400, detail="End date must be strictly after start date (cannot be the same day or earlier).")
    
    for field in ["mpesa_consumer_key", "mpesa_consumer_secret", "mpesa_initiator_password"]:
        if updates.get(field) == "********":
            if current and current.get(field):
                updates[field] = current[field]
            else:
                updates[field] = ""
                
    # 2. Check if phone_number is being changed
    if "phone_number" in updates and updates["phone_number"]:
        from app.api.routers.auth import sanitize_phone_number
        sanitized_phone = sanitize_phone_number(updates["phone_number"])
        current_phone = current.get("phone_number", "") if current else ""
        
        if current_phone and sanitize_phone_number(current_phone) != sanitized_phone:
            password = updates.pop("password", None) or payload.password
            otp_code = updates.pop("otp_code", None) or payload.otp_code
            if not password or not otp_code:
                raise HTTPException(
                    status_code=400,
                    detail="Both password and 6-digit OTP verification code are required to update your configured phone number."
                )
            from app.db.models import User
            user = db.session.query(User).filter(User.id == user_id).first()
            if not user or not db._verify_password(password, user.password_hash, user.salt):
                raise HTTPException(status_code=401, detail="Invalid password credential.")
            if not user.email:
                raise HTTPException(status_code=400, detail="User account does not have a verified email address. Please link an email address in Profile first.")
            
            is_valid_otp = db.verify_otp_challenge(user.email, otp_code, purpose="phone_update")
            if not is_valid_otp:
                is_valid_otp = db.verify_otp_challenge(user.email, otp_code, purpose="payout_stepup")
            if not is_valid_otp:
                raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
            
            client_ip = request.client.host if request.client else "127.0.0.1"
            db.log_event(user_id, "SECURITY", f"Phone number in settings updated from '{current_phone}' to '{sanitized_phone}' via step-up authentication.")
            db.create_admin_audit_log(
                admin_id=None,
                action="USER_PHONE_UPDATED",
                target_type="User",
                target_id=user_id,
                before_state=f'{{"phone_number": "{current_phone}"}}',
                after_state=f'{{"phone_number": "{sanitized_phone}"}}',
                reason="User updated phone number in settings",
                ip_address=client_ip
            )
        updates["phone_number"] = sanitized_phone

    updates.pop("password", None)
    updates.pop("otp_code", None)

    # 3. Validate payout_time format (HH:MM within 00:00 to 23:59)
    if "payout_time" in updates and updates["payout_time"]:
        payout_time_str = updates["payout_time"]
        if not re.match(r"^\d{2}:\d{2}$", payout_time_str):
            raise HTTPException(status_code=400, detail="Invalid payout time format. Must be HH:MM.")
        try:
            h, m = map(int, payout_time_str.split(":"))
            if h < 0 or h > 23 or m < 0 or m > 59:
                raise ValueError()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid hours or minutes in payout time.")

    db.update_settings(user_id, **updates)
    db.log_event(user_id, "INFO", "Wallet and API configuration updated.")
    
    res = db.get_settings(user_id)
    # Expose derived lock flags and masked sensitive fields in return payload
    res_dict = _mask_sensitive_fields(res) if res else {}
    res_dict["is_budget_locked"] = db.is_budget_locked(user_id)
    res_dict["is_deposit_locked"] = db.is_deposit_locked(user_id)
    return {"status": "success", "settings": res_dict}
