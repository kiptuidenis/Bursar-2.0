import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Body
from app.db.manager import DatabaseManager
from app.db.models import BudgetItem
from app.api.dependencies import get_db, get_current_user_id
from app.api.schemas import BudgetItemPayload, BudgetLockPayload

router = APIRouter(prefix="/api/budget", tags=["Budget"])

@router.get("/items")
def list_budget_items(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    return db.get_budget_items(user_id)

@router.post("/items")
def add_or_update_budget_item(payload: BudgetItemPayload, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if db.is_budget_locked(user_id):
        raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
    category = payload.category.strip()
    if not category:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
        
    # Check if this new daily budget would exceed balance (only if balance > 0)
    settings = db.get_settings(user_id)
    balance = settings.get("balance", 0.0)
    items = db.get_budget_items(user_id)
    other_sum = sum(item["amount"] for item in items if item["category"] != category)
    new_budget = other_sum + payload.amount
    if new_budget > balance and balance > 0:
        raise HTTPException(status_code=400, detail=f"Total daily budget (KES {new_budget:.2f}) cannot be more than your deposit balance (KES {balance:.2f}).")
        
    item_id = db.add_or_update_budget_item(user_id, category, payload.amount)
    return {"status": "success", "item_id": item_id, "daily_budget": db.get_settings(user_id).get("daily_budget", 0.0)}

@router.delete("/items/{item_id}")
def delete_budget_item(item_id: int, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if db.is_budget_locked(user_id):
        raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
    deleted = db.delete_budget_item(user_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Budget item not found")
    return {"status": "success", "daily_budget": db.get_settings(user_id).get("daily_budget", 0.0)}

@router.post("/lock")
def lock_budget_endpoint(payload: BudgetLockPayload = Body(default=None), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if payload is None:
        payload = BudgetLockPayload()
        
    if payload.items is not None:
        if db.is_budget_locked(user_id):
            raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
        db.session.query(BudgetItem).filter(BudgetItem.user_id == user_id).delete(synchronize_session=False)
        for item in payload.items:
            category = item.category.strip()
            if not category:
                raise HTTPException(status_code=400, detail="Category name cannot be empty")
            db_item = BudgetItem(user_id=user_id, category=category, amount=item.amount)
            db.session.add(db_item)
        db._commit()
        db.recalculate_daily_budget(user_id)
        
    items = db.get_budget_items(user_id)
    if not items:
        raise HTTPException(status_code=400, detail="Cannot lock an empty budget. Please create budget items first.")
        
    start_date = payload.start_date.strip() if payload.start_date else ""
    end_date = payload.end_date.strip() if payload.end_date else ""
    
    if start_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
            raise HTTPException(status_code=400, detail="Invalid start date format. Must be YYYY-MM-DD.")
    if end_date:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
            raise HTTPException(status_code=400, detail="Invalid end date format. Must be YYYY-MM-DD.")
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="End date cannot be earlier than start date.")
        
    settings = db.get_settings(user_id)
    daily_budget = settings.get("daily_budget", 0.0)
    balance = settings.get("balance", 0.0)
    if daily_budget > balance and balance > 0:
        raise HTTPException(status_code=400, detail=f"Daily budget (KES {daily_budget:.2f}) cannot be more than your deposit balance (KES {balance:.2f}).")
        
    db.lock_budget(user_id)
    db.update_settings(user_id, start_date=start_date, end_date=end_date)
    db.log_event(user_id, "INFO", f"Budget configuration locked until the end of the month with payout range {start_date or 'none'} to {end_date or 'none'}.")
    return {
        "status": "success", 
        "budget_locked_until": db.get_settings(user_id).get("budget_locked_until", ""),
        "start_date": start_date,
        "end_date": end_date
    }
