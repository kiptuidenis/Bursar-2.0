import re
import sqlalchemy
from typing import Optional
from app.db.models import User, Session as DbSession
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id, session_manager
from app.api.schemas import AuthPayload
from app.core.config import SESSION_COOKIE_SECURE
from app.services.recaptcha import verify_recaptcha_token

from app.core.limiter import limiter

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
@limiter.limit("5/minute")
def signup_user(request: Request, payload: AuthPayload, db: DatabaseManager = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    if not verify_recaptcha_token(payload.recaptcha_token, client_ip=client_ip):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    sanitized_phone = sanitize_phone_number(payload.phone_number)
    
    from app.core.password import validate_password_strength
    pwd_error = validate_password_strength(payload.password, user_context=sanitized_phone)
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)

    try:
        user_id = db.create_user(sanitized_phone, payload.password)
        db.log_event(user_id, "INFO", "User registration completed successfully.")
        return {"status": "success", "user_id": user_id}
    except sqlalchemy.exc.IntegrityError:
        raise HTTPException(status_code=400, detail="This phone number is already registered.")

@router.post("/login")
@limiter.limit("5/minute")
def login_user(request: Request, payload: AuthPayload, response: Response, db: DatabaseManager = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    if not verify_recaptcha_token(payload.recaptcha_token, client_ip=client_ip):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    sanitized_phone = sanitize_phone_number(payload.phone_number)

    # 1. Pre-check if account is locked due to 5+ failed attempts
    is_locked, remaining_secs = db.is_account_locked(sanitized_phone)
    if is_locked:
        remaining_mins = max(1, int(remaining_secs / 60))
        from fastapi.responses import JSONResponse
        resp = JSONResponse(
            status_code=429,
            content={"detail": f"Account locked. Try again in {remaining_mins} minutes."}
        )
        resp.headers["Retry-After"] = str(remaining_secs)
        return resp

    user_id = db.authenticate_user(sanitized_phone, payload.password)
    
    if not user_id:
        attempts, just_locked = db.record_failed_login_attempt(sanitized_phone)
        if just_locked:
            from fastapi.responses import JSONResponse
            resp = JSONResponse(
                status_code=429,
                content={"detail": "Account locked. Try again in 15 minutes."}
            )
            resp.headers["Retry-After"] = "900"
            return resp
        raise HTTPException(status_code=401, detail="Invalid phone number or password PIN.")
        
    db.reset_failed_login_attempts(sanitized_phone)
        
    user_agent = request.headers.get("user-agent", "Unknown Device")
    ip_address = request.client.host if request.client else "Unknown IP"
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db, user_agent=user_agent, ip_address=ip_address) # Valid for 24 hours
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=86400
    )
    db.log_event(user_id, "INFO", "User successfully authenticated.")
    return {"status": "success", "user_id": user_id}


@router.post("/logout")
def logout_user(response: Response, session_token: Optional[str] = Cookie(None), db: DatabaseManager = Depends(get_db)):
    response.delete_cookie(key="session_token", secure=SESSION_COOKIE_SECURE)
    if session_token:
        db.session.query(DbSession).filter(DbSession.session_token == session_token).delete(synchronize_session=False)
        db._commit()
    return {"status": "success"}

@router.get("/me")
def get_me(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    import datetime
    user = db.session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {
        "id": user.id,
        "phone_number": user.phone_number,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(user.created_at, datetime.datetime) else user.created_at
    }

@router.post("/ping")
def ping_session(user_id: int = Depends(get_current_user_id)):
    return {"status": "ok"}

@router.get("/config")
def get_auth_config():
    from app.core import config
    return {
        "recaptcha_enabled": config.RECAPTCHA_ENABLED and bool(config.RECAPTCHA_SITE_KEY) and config.RECAPTCHA_SITE_KEY != "your_recaptcha_site_key_here",
        "recaptcha_site_key": config.RECAPTCHA_SITE_KEY if config.RECAPTCHA_SITE_KEY != "your_recaptcha_site_key_here" else ""
    }

