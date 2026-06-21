import re
import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id, session_manager
from app.api.schemas import AuthPayload

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

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

@router.post("/signup")
def signup_user(payload: AuthPayload, db: DatabaseManager = Depends(get_db)):
    sanitized_phone = sanitize_phone_number(payload.phone_number)
    try:
        user_id = db.create_user(sanitized_phone, payload.password)
        db.log_event(user_id, "INFO", "User registration completed successfully.")
        return {"status": "success", "user_id": user_id}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="This phone number is already registered.")

@router.post("/login")
def login_user(payload: AuthPayload, response: Response, request: Request, db: DatabaseManager = Depends(get_db)):
    sanitized_phone = sanitize_phone_number(payload.phone_number)
    user_id = db.authenticate_user(sanitized_phone, payload.password)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid phone number or password PIN.")
        
    user_agent = request.headers.get("user-agent", "Unknown Device")
    ip_address = request.client.host if request.client else "Unknown IP"
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db, user_agent=user_agent, ip_address=ip_address) # Valid for 24 hours
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

@router.post("/logout")
def logout_user(response: Response, session_token: Optional[str] = Cookie(None), db: DatabaseManager = Depends(get_db)):
    response.delete_cookie(key="session_token")
    if session_token:
        conn = db.connection
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
        conn.commit()
    return {"status": "success"}

@router.get("/me")
def get_me(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    conn = db.connection
    cursor = conn.cursor()
    cursor.execute("SELECT id, phone_number, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return dict(row)
