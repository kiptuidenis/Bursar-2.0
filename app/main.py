import os
import re
import sys
import datetime
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Body, Cookie, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.db import DatabaseManager
from app.mpesa import MpesaClient
from app.auth import SessionManager
from app.scheduler import BackgroundScheduler, check_and_trigger_payout

# DB File Configuration
DB_FILE = "bursar.db"
db_manager = DatabaseManager(DB_FILE)

# Session Manager initialization (random keys generated automatically)
session_manager = SessionManager()

# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_manager.initialize()
    
    if "PYTEST_CURRENT_TEST" not in os.environ:
        app.state.scheduler = BackgroundScheduler(db_manager, interval_seconds=60)
        app.state.scheduler.start()
    else:
        app.state.scheduler = None
        
    yield
    
    if app.state.scheduler:
        app.state.scheduler.stop()
    db_manager.close()

app = FastAPI(lifespan=lifespan, title="Bursar 2.0 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db() -> DatabaseManager:
    return db_manager

# Dependency for authenticating users via HTTP-only cookie sessions
def get_current_user_id(
    session_token: Optional[str] = Cookie(None),
    db: DatabaseManager = Depends(get_db)
) -> int:
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication session required. Please log in.")
        
    user_id = session_manager.validate_session(session_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication session expired or invalid. Please log in again.")
        
    return user_id

# Phone Number Sanitization Helper
def sanitize_phone_number(phone: str) -> str:
    phone = phone.strip()
    if phone.startswith("+"):
        phone = phone[1:]
    # Convert local 07... / 01... formats to international 2547... / 2541...
    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]
        
    if not re.match(r"^254[71]\d{8}$", phone):
        raise HTTPException(
            status_code=400, 
            detail="Invalid Safaricom phone number. Must start with 2547, 2541, 07, or 01 followed by 8 digits."
        )
    return phone

# Pydantic input models
class AuthPayload(BaseModel):
    phone_number: str = Field(..., description="Safaricom phone number (e.g. 254712345678 or 0712345678)")
    password: str = Field(..., min_length=4, description="Password PIN (minimum 4 characters)")

class SettingsUpdate(BaseModel):
    balance: Optional[float] = None
    daily_budget: Optional[float] = None
    phone_number: Optional[str] = None
    payout_time: Optional[str] = None
    mode: Optional[str] = None
    mpesa_consumer_key: Optional[str] = None
    mpesa_consumer_secret: Optional[str] = None
    mpesa_shortcode: Optional[str] = None
    mpesa_initiator_name: Optional[str] = None
    mpesa_initiator_password: Optional[str] = None
    mpesa_b2c_result_url: Optional[str] = None
    mpesa_b2c_timeout_url: Optional[str] = None

class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to deposit must be greater than zero")


class BudgetItemPayload(BaseModel):
    category: str = Field(..., min_length=1, max_length=100, description="Budget category name")
    amount: float = Field(..., gt=0, description="Amount allocated to category must be greater than zero")


# API Routing — Authentication (Public)
@app.post("/api/auth/signup")
def signup_user(payload: AuthPayload, db: DatabaseManager = Depends(get_db)):
    sanitized_phone = sanitize_phone_number(payload.phone_number)
    try:
        user_id = db.create_user(sanitized_phone, payload.password)
        db.log_event(user_id, "INFO", "User registration completed successfully.")
        return {"status": "success", "user_id": user_id}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="This phone number is already registered.")

@app.post("/api/auth/login")
def login_user(payload: AuthPayload, response: Response, db: DatabaseManager = Depends(get_db)):
    sanitized_phone = sanitize_phone_number(payload.phone_number)
    user_id = db.authenticate_user(sanitized_phone, payload.password)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid phone number or password PIN.")
        
    token = session_manager.create_session(user_id, expires_in_seconds=86400) # Valid for 24 hours
    # Set HTTP-only secure cookie session
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400
    )
    db.log_event(user_id, "INFO", "User successfully authenticated.")
    return {"status": "success", "user_id": user_id}

@app.post("/api/auth/logout")
def logout_user(response: Response):
    response.delete_cookie(key="session_token")
    return {"status": "success"}

@app.get("/api/auth/me")
def get_me(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    conn = db.connection
    cursor = conn.cursor()
    cursor.execute("SELECT id, phone_number, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return dict(row)


# API Routing — Protected Operations (Requires Session Cookie)
@app.get("/api/settings")
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
    masked["is_budget_locked"] = db.is_budget_locked(user_id)
    masked["is_deposit_locked"] = db.is_deposit_locked(user_id)
    return masked

@app.post("/api/settings")
def update_settings(payload: SettingsUpdate, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No settings provided to update")
        
    current = db.get_settings(user_id)
    
    # 1. Enforce budget lock on daily_budget updates
    if "daily_budget" in updates:
        new_val = updates["daily_budget"]
        old_val = current.get("daily_budget", 0.0) if current else 0.0
        if new_val != old_val and db.is_budget_locked(user_id):
            raise HTTPException(status_code=400, detail="Daily budget is locked until the end of the month.")
            
    # 2. Enforce deposit lock on balance updates (reject decreases)
    if "balance" in updates:
        new_bal = updates["balance"]
        old_bal = current.get("balance", 0.0) if current else 0.0
        if new_bal < old_bal and db.is_deposit_locked(user_id):
            raise HTTPException(status_code=400, detail="Deposits are locked and balance cannot be manually decreased until the end of the month.")
            
    for field in ["mpesa_consumer_secret", "mpesa_initiator_password"]:
        if updates.get(field) == "********":
            if current and current.get(field):
                updates[field] = current[field]
            else:
                updates[field] = ""
                
    db.update_settings(user_id, **updates)
    db.log_event(user_id, "INFO", "Wallet and API configuration updated.")
    
    res = db.get_settings(user_id)
    # Expose derived lock flags in return payload
    res_dict = dict(res) if res else {}
    res_dict["is_budget_locked"] = db.is_budget_locked(user_id)
    res_dict["is_deposit_locked"] = db.is_deposit_locked(user_id)
    return {"status": "success", "settings": res_dict}

@app.post("/api/deposit")
def deposit_funds(payload: DepositRequest, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    db.adjust_balance(user_id, payload.amount)
    db.log_event(user_id, "INFO", f"Deposited KES {payload.amount:.2f} into wallet.")
    
    # Auto-lock deposit for the month
    db.lock_deposit(user_id)
    
    # Auto-lock budget if user already has budget categories configured
    items = db.get_budget_items(user_id)
    if items:
        db.lock_budget(user_id)
        db.log_event(user_id, "INFO", "Budget automatically locked due to active deposit.")
        
    settings = db.get_settings(user_id)
    new_balance = settings.get("balance", 0.0)
    return {
        "status": "success", 
        "new_balance": new_balance,
        "is_budget_locked": db.is_budget_locked(user_id),
        "is_deposit_locked": db.is_deposit_locked(user_id)
    }

@app.get("/api/payouts")
def list_payouts(limit: int = 100, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    return db.get_payouts(user_id, limit=limit)

@app.get("/api/logs")
def list_logs(limit: int = 100, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    return db.get_logs(user_id, limit=limit)


@app.get("/api/budget/items")
def list_budget_items(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    return db.get_budget_items(user_id)


@app.post("/api/budget/items")
def add_or_update_budget_item(payload: BudgetItemPayload, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if db.is_budget_locked(user_id):
        raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
    category = payload.category.strip()
    if not category:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
        
    item_id = db.add_or_update_budget_item(user_id, category, payload.amount)
    return {"status": "success", "item_id": item_id, "daily_budget": db.get_settings(user_id).get("daily_budget", 0.0)}


@app.delete("/api/budget/items/{item_id}")
def delete_budget_item(item_id: int, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if db.is_budget_locked(user_id):
        raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
    deleted = db.delete_budget_item(user_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Budget item not found")
    return {"status": "success", "daily_budget": db.get_settings(user_id).get("daily_budget", 0.0)}

@app.post("/api/budget/lock")
def lock_budget_endpoint(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    items = db.get_budget_items(user_id)
    if not items:
        raise HTTPException(status_code=400, detail="Cannot lock an empty budget. Please create budget items first.")
    db.lock_budget(user_id)
    db.log_event(user_id, "INFO", "Budget configuration locked until the end of the month.")
    return {"status": "success", "budget_locked_until": db.get_settings(user_id).get("budget_locked_until", "")}

@app.post("/api/payout/trigger")
async def trigger_payout_manually(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    settings = db.get_settings(user_id)
    client = MpesaClient(
        consumer_key=settings.get("mpesa_consumer_key", ""),
        consumer_secret=settings.get("mpesa_consumer_secret", ""),
        shortcode=settings.get("mpesa_shortcode", ""),
        initiator_name=settings.get("mpesa_initiator_name", ""),
        initiator_password=settings.get("mpesa_initiator_password", ""),
        mode=settings.get("mode", "simulation")
    )
    
    now = datetime.datetime.now()
    triggered = await check_and_trigger_payout(db, client, now, user_id=user_id)
    return {"triggered": triggered}


# Safaricom M-Pesa API Callbacks (Public Webhooks — Authenticated via ConversationID lookup)
@app.post("/api/callbacks/b2c-result")
def mpesa_b2c_result_callback(body: Dict[str, Any] = Body(...), db: DatabaseManager = Depends(get_db)):
    result = body.get("Result")
    if not result:
        return {"status": "ignored"}
        
    conversation_id = result.get("ConversationID", "")
    result_code = result.get("ResultCode")
    result_desc = result.get("ResultDesc", "")
    transaction_id = result.get("TransactionID", "")
    
    # Locate matching pending payout record across all users
    matching_payout = db.get_payout_by_conversation_id(conversation_id)
            
    if not matching_payout or matching_payout["status"] != "PENDING":
        return {"status": "ignored"}
        
    user_id = matching_payout["user_id"]
    payout_amount = matching_payout["amount"]
    payout_date = matching_payout["payout_date"]
    
    if result_code == 0:
        db.update_payout_status(
            conversation_id=conversation_id,
            status="SUCCESS",
            transaction_id=transaction_id,
            error_message=""
        )
        db.log_event(user_id, "INFO", f"M-Pesa B2C payout of KES {payout_amount:.2f} for date {payout_date} was completed successfully. Receipt: {transaction_id}.")
    else:
        db.update_payout_status(
            conversation_id=conversation_id,
            status="FAILED",
            transaction_id="",
            error_message=result_desc
        )
        db.adjust_balance(user_id, payout_amount)
        db.log_event(user_id, "ERROR", f"M-Pesa B2C payout failed for date {payout_date}. Reason: {result_desc}. KES {payout_amount:.2f} refunded.")
        
    return {"status": "acknowledged"}

@app.post("/api/callbacks/b2c-timeout")
def mpesa_b2c_timeout_callback(body: Dict[str, Any] = Body(...), db: DatabaseManager = Depends(get_db)):
    conversation_id = body.get("ConversationID", "")
    result_desc = body.get("ResultDesc", "Transaction timed out at Safaricom Queue.")
    
    matching_payout = db.get_payout_by_conversation_id(conversation_id)
            
    if not matching_payout or matching_payout["status"] != "PENDING":
        return {"status": "ignored"}
        
    user_id = matching_payout["user_id"]
    payout_amount = matching_payout["amount"]
    payout_date = matching_payout["payout_date"]
    
    db.update_payout_status(
        conversation_id=conversation_id,
        status="FAILED",
        transaction_id="",
        error_message=result_desc
    )
    db.adjust_balance(user_id, payout_amount)
    db.log_event(user_id, "ERROR", f"M-Pesa B2C payout timed out for date {payout_date}. Reason: {result_desc}. KES {payout_amount:.2f} refunded.")
    
    return {"status": "acknowledged"}


# Mount static assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
