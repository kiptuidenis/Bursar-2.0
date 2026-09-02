import re
import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Body, Request
from app.db.manager import DatabaseManager
from app.db.models import BudgetItem
from app.api.dependencies import get_db, get_current_user_id
from app.api.schemas import BudgetItemPayload, BudgetLockPayload
from app.core.limiter import limiter

router = APIRouter(prefix="/api/budget", tags=["Budget"])

@router.get("/items")
@limiter.limit("60/minute")
def list_budget_items(request: Request, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    return db.get_budget_items(user_id)

@router.post("/items")
@limiter.limit("20/minute")
def add_or_update_budget_item(request: Request, payload: BudgetItemPayload, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if db.is_budget_locked(user_id):
        settings = db.get_settings(user_id)
        balance = int(settings.get("balance", 0)) if settings else 0
        if balance > 0:
            raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
    if not float(payload.amount).is_integer():
        raise HTTPException(status_code=400, detail="Budget allocation amount must be a whole positive integer (no decimal places).")
        
    category = payload.category.strip()
    if not category:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
        
    # Check if this new daily budget would exceed balance (only if balance > 0)
    settings = db.get_settings(user_id)
    balance = int(settings.get("balance", 0))
    items = db.get_budget_items(user_id)
    other_sum = sum(int(item["amount"]) for item in items if item["category"] != category)
    new_budget = other_sum + int(payload.amount)
    if new_budget > balance and balance > 0:
        raise HTTPException(status_code=400, detail=f"Total daily budget (KES {new_budget}) cannot be more than your deposit balance (KES {balance}).")
        
    item_id = db.add_or_update_budget_item(user_id, category, int(payload.amount))
    return {"status": "success", "item_id": item_id, "daily_budget": int(db.get_settings(user_id).get("daily_budget", 0))}

@router.delete("/items/{item_id}")
@limiter.limit("20/minute")
def delete_budget_item(request: Request, item_id: int, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if db.is_budget_locked(user_id):
        settings = db.get_settings(user_id)
        balance = int(settings.get("balance", 0)) if settings else 0
        if balance > 0:
            raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
    deleted = db.delete_budget_item(user_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Budget item not found")
    return {"status": "success", "daily_budget": int(db.get_settings(user_id).get("daily_budget", 0))}

@router.post("/lock")
@limiter.limit("10/minute")
def lock_budget_endpoint(request: Request, payload: BudgetLockPayload = Body(default=None), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if payload is None:
        payload = BudgetLockPayload()
        
    # 1. Determine incoming items and validate structure
    items_to_persist = None
    if payload.items is not None:
        if db.is_budget_locked(user_id):
            raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        if not payload.items:
            raise HTTPException(status_code=400, detail="Cannot lock an empty budget. Please create budget items first.")
        
        parsed_items = []
        for item in payload.items:
            if not float(item.amount).is_integer() or int(item.amount) <= 0:
                raise HTTPException(status_code=400, detail="Budget allocation amount must be a whole positive integer (no decimal places).")
            category = item.category.strip()
            if not category:
                raise HTTPException(status_code=400, detail="Category name cannot be empty.")
            parsed_items.append({"category": category, "amount": int(item.amount)})
        
        items_to_persist = parsed_items
        effective_daily_budget = sum(it["amount"] for it in parsed_items)
    else:
        existing_items = db.get_budget_items(user_id)
        if not existing_items:
            raise HTTPException(status_code=400, detail="Cannot lock an empty budget. Please create budget items first.")
        effective_daily_budget = sum(int(it["amount"]) for it in existing_items)

    # 2. Validate schedule dates
    start_date = payload.start_date.strip() if payload.start_date else ""
    end_date = payload.end_date.strip() if payload.end_date else ""
    
    today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d")
    
    if start_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
            raise HTTPException(status_code=400, detail="Invalid start date format. Must be YYYY-MM-DD.")
        if start_date <= today_str:
            raise HTTPException(status_code=400, detail="Start date must be in the future (tomorrow or later).")
    if end_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
            raise HTTPException(status_code=400, detail="Invalid end date format. Must be YYYY-MM-DD.")
    if start_date and end_date and end_date <= start_date:
        raise HTTPException(status_code=400, detail="End date must be strictly after start date (cannot be the same day or earlier).")
        
    # 3. Payout Phone Number Configuration & Step-up Authentication
    current_payout_phone = db.get_payout_phone_number(user_id)
    sanitized_phone = None
    if payload.payout_phone_number:
        from app.api.routers.auth import sanitize_phone_number
        sanitized_phone = sanitize_phone_number(payload.payout_phone_number)
        
        # If user is changing an already configured payout phone, enforce step-up
        if current_payout_phone and current_payout_phone != sanitized_phone:
            if not payload.password or not payload.otp_code:
                raise HTTPException(
                    status_code=400,
                    detail="Both password and 6-digit OTP verification code are required to update your configured payout phone number."
                )
            from app.db.models import User
            user = db.session.query(User).filter(User.id == user_id).first()
            if not user or not db._verify_password(payload.password, user.password_hash, user.salt):
                raise HTTPException(status_code=401, detail="Invalid password credential.")
            if not user.email:
                raise HTTPException(status_code=400, detail="User account does not have a verified email address. Please link an email address in Profile first.")
            
            is_valid_otp = db.verify_otp_challenge(user.email, payload.otp_code, purpose="payout_stepup")
            if not is_valid_otp:
                raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    elif not current_payout_phone:
        raise HTTPException(
            status_code=400,
            detail="A target Safaricom M-Pesa phone number is required to receive your daily disbursements. Please provide a payout phone number."
        )

    # 4. Validate wallet balance against effective daily budget
    settings = db.get_settings(user_id)
    balance = float(settings.get("balance", 0.0) or 0.0)
    if balance <= 0:
        raise HTTPException(status_code=400, detail="Cannot schedule or lock budget with zero wallet balance. Please deposit funds first.")
    if effective_daily_budget > balance:
        raise HTTPException(status_code=400, detail=f"Daily budget (KES {effective_daily_budget:.2f}) cannot be more than your deposit balance (KES {balance:.2f}).")

    # 5. ALL VALIDATIONS PASSED -> ATOMIC PERSISTENCE
    if items_to_persist is not None:
        db.session.query(BudgetItem).filter(BudgetItem.user_id == user_id).delete(synchronize_session=False)
        for it in items_to_persist:
            db_item = BudgetItem(user_id=user_id, category=it["category"], amount=float(it["amount"]))
            db.session.add(db_item)
        db._commit()
        db.recalculate_daily_budget(user_id)

    if sanitized_phone:
        if current_payout_phone and current_payout_phone != sanitized_phone:
            client_ip = request.client.host if request.client else "127.0.0.1"
            db.log_event(user_id, "SECURITY", f"Payout phone number updated from '{current_payout_phone}' to '{sanitized_phone}' via step-up authentication.")
            db.create_admin_audit_log(
                admin_id=None,
                action="USER_PAYOUT_PHONE_UPDATED",
                target_type="User",
                target_id=user_id,
                before_state=f'{{"payout_phone": "{current_payout_phone}"}}',
                after_state=f'{{"payout_phone": "{sanitized_phone}"}}',
                reason="User updated payout destination line during budget lock",
                ip_address=client_ip
            )
        db.update_payout_phone_number(user_id, sanitized_phone)

    db.lock_budget(user_id)
    db.update_settings(user_id, start_date=start_date, end_date=end_date)
    db.log_event(user_id, "INFO", f"Budget configuration locked until the end of the month with payout range {start_date or 'none'} to {end_date or 'none'}.")
    return {
        "status": "success", 
        "budget_locked_until": db.get_settings(user_id).get("budget_locked_until", ""),
        "start_date": start_date,
        "end_date": end_date
    }
