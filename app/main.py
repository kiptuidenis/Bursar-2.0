import os
import re
import sys
import datetime
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
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
    start_date: Optional[str] = None
    end_date: Optional[str] = None

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
    is_locked = db.is_budget_locked(user_id)
    masked["is_budget_locked"] = is_locked
    masked["is_deposit_locked"] = db.is_deposit_locked(user_id)
    return masked

@app.post("/api/settings")
def update_settings(payload: SettingsUpdate, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
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
                
            now = datetime.datetime.now()
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

@app.post("/api/deposit/initiate")
async def initiate_deposit(payload: DepositRequest, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    import uuid
    from app import payment_gateway
    
    settings = db.get_settings(user_id)
    phone = settings.get("phone_number", "")
    if not phone:
        raise HTTPException(status_code=400, detail="Target phone number must be configured in settings before depositing.")
        
    api_ref = f"DEP_{uuid.uuid4().hex[:12]}"
    
    try:
        res = await payment_gateway.initiate_stk_push(
            phone_number=phone,
            amount=payload.amount,
            api_ref=api_ref,
            user_settings=dict(settings) if settings else {}
        )
        
        response_code = res.get("ResponseCode", "")
        if response_code == "0":
            checkout_request_id = res.get("CheckoutRequestID", "")
            db.create_deposit(user_id, checkout_request_id, payload.amount)
            db.log_event(user_id, "INFO", f"STK Push deposit request of KES {payload.amount:.2f} initiated. CheckoutRequestID: {checkout_request_id}.")
            return {"status": "success", "checkout_request_id": checkout_request_id}
        else:
            desc = res.get("ResponseDescription", "LNM API Error")
            raise Exception(desc)
            
    except Exception as e:
        db.log_event(user_id, "ERROR", f"Failed to initiate STK Push: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate deposit payment: {str(e)}")

@app.get("/api/deposit/status/{checkout_request_id}")
async def check_deposit_status(checkout_request_id: str, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    deposit = db.get_deposit(checkout_request_id)
    if not deposit or deposit["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Deposit transaction not found.")
        
    if deposit["status"] == "PENDING":
        from app import payment_gateway
        settings = db.get_settings(user_id)
        try:
            gateway_res = await payment_gateway.check_stk_status(checkout_request_id, dict(settings) if settings else {})
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                db.update_deposit_status(checkout_request_id, "SUCCESS", "POLL_VERIFIED")
                db.adjust_balance(user_id, deposit["amount"])
                db.log_event(user_id, "INFO", f"Deposit {checkout_request_id} verified as SUCCESS via active polling.")
                
                db.lock_deposit(user_id)
                items = db.get_budget_items(user_id)
                if items:
                    db.lock_budget(user_id)
                    db.log_event(user_id, "INFO", "Budget automatically locked due to active deposit.")
                    
                deposit = db.get_deposit(checkout_request_id)
            elif status == "FAILED":
                db.update_deposit_status(checkout_request_id, "FAILED", "POLL_FAILED")
                db.log_event(user_id, "INFO", f"Deposit {checkout_request_id} marked as FAILED via active polling.")
                deposit = db.get_deposit(checkout_request_id)
        except Exception as e:
            db.log_event(user_id, "WARNING", f"Failed to poll gateway status for {checkout_request_id}: {str(e)}")
            
    return {"status": deposit["status"], "checkout_request_id": checkout_request_id}

@app.post("/api/callbacks/stk-callback")
def mpesa_stk_callback(body: Dict[str, Any] = Body(...), db: DatabaseManager = Depends(get_db)):
    stk_callback = body.get("Body", {}).get("stkCallback", {})
    if not stk_callback:
        return {"status": "ignored"}
        
    checkout_request_id = stk_callback.get("CheckoutRequestID", "")
    result_code = stk_callback.get("ResultCode")
    result_desc = stk_callback.get("ResultDesc", "")
    
    deposit = db.get_deposit(checkout_request_id)
    if not deposit or deposit["status"] != "PENDING":
        return {"status": "ignored"}
        
    user_id = deposit["user_id"]
    amount = deposit["amount"]
    
    if result_code == 0:
        # Get Mpesa Receipt Number
        receipt = ""
        meta_items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
        for item in meta_items:
            if item.get("Name") == "MpesaReceiptNumber":
                receipt = item.get("Value", "")
                break
                
        db.update_deposit_status(checkout_request_id, "SUCCESS", receipt)
        db.adjust_balance(user_id, amount)
        db.log_event(user_id, "INFO", f"STK Push deposit of KES {amount:.2f} completed successfully. Receipt: {receipt}.")
        
        # Auto-lock deposit for the month
        db.lock_deposit(user_id)
        
        # Auto-lock budget if user already has budget categories configured
        items = db.get_budget_items(user_id)
        if items:
            db.lock_budget(user_id)
            db.log_event(user_id, "INFO", "Budget automatically locked due to active deposit.")
    else:
        db.update_deposit_status(checkout_request_id, "FAILED")
        db.log_event(user_id, "ERROR", f"STK Push deposit failed. Reason: {result_desc}.")
        
    return {"status": "acknowledged"}

@app.post("/api/deposit/simulate-callback")
def simulate_stk_callback(payload: Dict[str, Any] = Body(...), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    import uuid
    # Local endpoint to fake a Safaricom callback response for test environment simulation
    checkout_request_id = payload.get("checkout_request_id", "")
    status = payload.get("status", "SUCCESS").upper()
    
    deposit = db.get_deposit(checkout_request_id)
    if not deposit or deposit["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Deposit transaction not found.")
        
    if deposit["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="Transaction already processed.")
        
    amount = deposit["amount"]
    
    if status == "SUCCESS":
        receipt = payload.get("receipt_number", f"MOCK{uuid.uuid4().hex[:6].upper()}")
        db.update_deposit_status(checkout_request_id, "SUCCESS", receipt)
        db.adjust_balance(user_id, amount)
        db.log_event(user_id, "INFO", f"[SIMULATED] STK Push deposit of KES {amount:.2f} completed successfully. Receipt: {receipt}.")
        
        # Auto-lock deposit
        db.lock_deposit(user_id)
        
        # Auto-lock budget
        items = db.get_budget_items(user_id)
        if items:
            db.lock_budget(user_id)
            db.log_event(user_id, "INFO", "Budget automatically locked due to simulated active deposit.")
    else:
        db.update_deposit_status(checkout_request_id, "FAILED")
        db.log_event(user_id, "ERROR", f"[SIMULATED] STK Push deposit failed.")
        
    return {"status": "success"}

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

class DraftBudgetItem(BaseModel):
    category: str = Field(..., min_length=1, max_length=100, description="Category name")
    amount: float = Field(..., gt=0, description="Allocation amount")

class BudgetLockPayload(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    items: Optional[List[DraftBudgetItem]] = None

@app.post("/api/budget/lock")
def lock_budget_endpoint(payload: BudgetLockPayload = Body(default=None), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if payload is None:
        payload = BudgetLockPayload()
        
    if payload.items is not None:
        if db.is_budget_locked(user_id):
            raise HTTPException(status_code=400, detail="Budget is locked until the end of the month.")
        
        conn = db.connection
        cursor = conn.cursor()
        cursor.execute("DELETE FROM budget_items WHERE user_id = ?", (user_id,))
        for item in payload.items:
            category = item.category.strip()
            if not category:
                raise HTTPException(status_code=400, detail="Category name cannot be empty")
            cursor.execute("""
                INSERT INTO budget_items (user_id, category, amount)
                VALUES (?, ?, ?)
            """, (user_id, category, item.amount))
        conn.commit()
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
        
    db.lock_budget(user_id)
    db.update_settings(user_id, start_date=start_date, end_date=end_date)
    db.log_event(user_id, "INFO", f"Budget configuration locked until the end of the month with payout range {start_date or 'none'} to {end_date or 'none'}.")
    return {
        "status": "success", 
        "budget_locked_until": db.get_settings(user_id).get("budget_locked_until", ""),
        "start_date": start_date,
        "end_date": end_date
    }

@app.post("/api/payout/trigger")
async def trigger_payout_manually(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    from app.config import (
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


@app.post("/api/callbacks/intasend-webhook")
async def intasend_webhook(body: Dict[str, Any] = Body(...), db: DatabaseManager = Depends(get_db)):
    invoice_id = body.get("invoice_id")
    tracking_id = body.get("tracking_id")
    
    if invoice_id:
        deposit = db.get_deposit(invoice_id)
        if not deposit or deposit["status"] != "PENDING":
            return {"status": "ignored"}
            
        user_id = deposit["user_id"]
        amount = deposit["amount"]
        
        from app import payment_gateway
        settings = db.get_settings(user_id)
        try:
            gateway_res = await payment_gateway.check_stk_status(invoice_id, dict(settings) if settings else {})
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                db.update_deposit_status(invoice_id, "SUCCESS", "WEBHOOK_VERIFIED")
                db.adjust_balance(user_id, amount)
                db.log_event(user_id, "INFO", f"IntaSend deposit of KES {amount:.2f} completed successfully (verified). Invoice: {invoice_id}.")
                
                db.lock_deposit(user_id)
                items = db.get_budget_items(user_id)
                if items:
                    db.lock_budget(user_id)
                    db.log_event(user_id, "INFO", "Budget automatically locked due to active deposit.")
            elif status == "FAILED":
                db.update_deposit_status(invoice_id, "FAILED")
                db.log_event(user_id, "ERROR", f"IntaSend deposit failed (verified). Invoice: {invoice_id}.")
        except Exception as e:
            db.log_event(user_id, "WARNING", f"Webhook double-check failed for invoice {invoice_id}: {str(e)}")
            
    elif tracking_id:
        matching_payout = db.get_payout_by_conversation_id(tracking_id)
        if not matching_payout or matching_payout["status"] != "PENDING":
            return {"status": "ignored"}
            
        user_id = matching_payout["user_id"]
        payout_amount = matching_payout["amount"]
        payout_date = matching_payout["payout_date"]
        
        from app import payment_gateway
        settings = db.get_settings(user_id)
        try:
            gateway_res = await payment_gateway.check_payout_status(tracking_id, dict(settings) if settings else {})
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                db.update_payout_status(
                    conversation_id=tracking_id,
                    status="SUCCESS",
                    transaction_id=tracking_id,
                    error_message=""
                )
                db.log_event(user_id, "INFO", f"IntaSend payout of KES {payout_amount:.2f} for date {payout_date} was completed successfully (verified). Payout ID: {tracking_id}.")
            elif status == "FAILED":
                db.update_payout_status(
                    conversation_id=tracking_id,
                    status="FAILED",
                    transaction_id="",
                    error_message="IntaSend disbursement failed"
                )
                db.adjust_balance(user_id, payout_amount)
                db.log_event(user_id, "ERROR", f"IntaSend payout failed (verified) for date {payout_date}. KES {payout_amount:.2f} refunded.")
        except Exception as e:
            db.log_event(user_id, "WARNING", f"Webhook double-check failed for payout tracking_id {tracking_id}: {str(e)}")
            
    return {"status": "acknowledged"}


@app.get("/api/diagnostics")
async def get_diagnostics():
    import subprocess
    try:
        commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        commit_hash = "unknown"
    return {
        "version": "1.2.0",
        "commit_hash": commit_hash,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }


@app.get("/dashboard")
def get_dashboard_page():
    from fastapi.responses import FileResponse
    dashboard_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    raise HTTPException(status_code=404, detail="Dashboard not found")


# Mount static assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
