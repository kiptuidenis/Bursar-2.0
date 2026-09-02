import re
import logging
import sqlalchemy
from typing import Optional
from app.db.models import User, Session as DbSession
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id, session_manager
from app.api.schemas import AuthPayload, AuthLoginPayload
from app.core.config import SESSION_COOKIE_SECURE
from app.services.recaptcha import verify_recaptcha_token

from app.core.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])




EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

def sanitize_phone_number(phone: str) -> str:
    phone = phone.strip()
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]
        
    if not re.match(r"^254[71]\d{8}$", phone):
        raise HTTPException(
            status_code=400, 
            detail="Invalid Safaricom phone number. Must start with 2547, 2541, 07, or 01 followed by 8 digits."
        )
    return phone

from app.api.schemas import AuthPayload, AuthLoginPayload, OTPVerificationPayload, OTPResendPayload
from app.services.email import send_otp_email

@router.post("/signup")
@limiter.limit("5/minute")
def signup_user(request: Request, payload: AuthPayload, response: Response, db: DatabaseManager = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    if not verify_recaptcha_token(payload.recaptcha_token, client_ip=client_ip):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    if not payload.email or not payload.email.strip():
        raise HTTPException(
            status_code=400,
            detail="Registration using phone numbers is disabled. Please register with a valid email address."
        )

    email_clean = payload.email.strip().lower()
    if not re.match(EMAIL_REGEX, email_clean):
        raise HTTPException(status_code=400, detail="Invalid email address format.")
        
    from app.core.password import validate_password_strength
    pwd_error = validate_password_strength(payload.password, user_context=email_clean)
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)

    existing = db.get_user_by_email(email_clean)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email address already exists.")

    try:
        password_hash, salt = db._hash_password(payload.password)
        stored_cred = f"{password_hash}:{salt}"

        otp_code = db.create_otp_challenge(
            email_clean,
            purpose="signup_2fa",
            ttl_seconds=300,
            password_hash=stored_cred
        )
        send_otp_email(email_clean, otp_code, purpose="signup_2fa")

        return {
            "status": "2fa_required",
            "email": email_clean,
            "purpose": "signup_2fa",
            "message": "Verification code sent to your email."
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Registration error for email '{email_clean}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again later.")

@router.post("/login")
@limiter.limit("5/minute")
def login_user(request: Request, payload: AuthLoginPayload, response: Response, db: DatabaseManager = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    if not verify_recaptcha_token(payload.recaptcha_token, client_ip=client_ip):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    if not payload.email and not payload.phone_number:
        raise HTTPException(status_code=422, detail="Email address or phone number is required.")

    # Check Email Login vs Legacy Phone Login
    if payload.email:
        email_clean = payload.email.strip().lower()
        user = db.get_user_by_email(email_clean)
        
        # Pre-check account lockout
        is_locked, remaining_secs = db.is_account_locked(email_clean)
        if is_locked:
            remaining_mins = max(1, int(remaining_secs / 60))
            from fastapi.responses import JSONResponse
            resp = JSONResponse(
                status_code=429,
                content={"detail": f"Account locked. Try again in {remaining_mins} minutes."}
            )
            resp.headers["Retry-After"] = str(remaining_secs)
            return resp

        if not user or not db._verify_password(payload.password, user.password_hash, user.salt):
            attempts, just_locked = db.record_failed_login_attempt(email_clean)
            if just_locked:
                from fastapi.responses import JSONResponse
                resp = JSONResponse(
                    status_code=429,
                    content={"detail": "Account locked. Try again in 15 minutes."}
                )
                resp.headers["Retry-After"] = "900"
                return resp
            raise HTTPException(status_code=401, detail="Invalid email address or password.")

        # Password verified! Generate 6-digit Email OTP challenge
        otp_code = db.create_otp_challenge(email_clean, purpose="login_2fa", ttl_seconds=300, user_id=user.id)
        send_otp_email(email_clean, otp_code, purpose="login_2fa")

        return {
            "status": "2fa_required",
            "email": email_clean,
            "purpose": "login_2fa",
            "message": "Two-factor verification code sent to your email."
        }

    # Legacy Phone Login Handler
    if payload.phone_number:
        sanitized_phone = sanitize_phone_number(payload.phone_number)
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
            raise HTTPException(status_code=401, detail="Invalid email address or password.")

        db.reset_failed_login_attempts(sanitized_phone)
            
        user_agent = request.headers.get("user-agent", "Unknown Device")
        ip_address = request.client.host if request.client else "Unknown IP"
        token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db, user_agent=user_agent, ip_address=ip_address)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=SESSION_COOKIE_SECURE,
            samesite="lax",
            max_age=86400
        )
        
        from app.core.csrf import generate_csrf_token
        new_csrf = generate_csrf_token()
        response.set_cookie(
            key="csrf_token",
            value=new_csrf,
            httponly=False,
            secure=SESSION_COOKIE_SECURE,
            samesite="lax",
            path="/"
        )
        db.log_event(user_id, "INFO", "User successfully authenticated.")
        return {"status": "success", "user_id": user_id}

    raise HTTPException(status_code=422, detail="Email address or phone number is required.")

@router.post("/verify-otp")
@limiter.limit("10/minute")
def verify_otp(request: Request, payload: OTPVerificationPayload, response: Response, db: DatabaseManager = Depends(get_db)):
    email_clean = payload.email.strip().lower()

    if payload.purpose == "signup_2fa":
        otp_rec = db.get_otp_record(email_clean, payload.purpose)
        if not otp_rec or not otp_rec.password_hash:
            raise HTTPException(status_code=400, detail="Invalid or expired verification session. Please register again.")

        stored_cred = otp_rec.password_hash
        parts = stored_cred.split(":")
        password_hash = parts[0]
        salt = parts[1] if len(parts) > 1 else "argon2"

        is_valid = db.verify_otp_challenge(email_clean, payload.otp_code, payload.purpose)
        if not is_valid:
            raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

        existing = db.get_user_by_email(email_clean)
        if existing:
            raise HTTPException(status_code=400, detail="An account with this email address already exists.")
        
        user_id = db.create_user_email(email_clean, password_hash, salt)
        user = db.get_user_by_email(email_clean)
    else:
        is_valid = db.verify_otp_challenge(email_clean, payload.otp_code, payload.purpose)
        if not is_valid:
            raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

        user = db.get_user_by_email(email_clean)
        if not user:
            raise HTTPException(status_code=404, detail="User account not found.")

    if user and not user.email_verified:
        user.email_verified = True
        db._commit()

    db.reset_failed_login_attempts(email_clean)
    user_agent = request.headers.get("user-agent", "Unknown Device")
    ip_address = request.client.host if request.client else "Unknown IP"
    token = session_manager.create_session(user.id, expires_in_seconds=86400, db=db, user_agent=user_agent, ip_address=ip_address)

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=86400
    )
    from app.core.csrf import generate_csrf_token
    new_csrf = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=new_csrf,
        httponly=False,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/"
    )

    db.log_event(user.id, "INFO", f"OTP verification successful for purpose '{payload.purpose}'. Session issued.")
    return {
        "status": "success",
        "user_id": user.id,
        "email": user.email,
        "email_verified": user.email_verified
    }

@router.post("/resend-otp")
@limiter.limit("3/minute")
def resend_otp(request: Request, payload: OTPResendPayload, db: DatabaseManager = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = db.get_user_by_email(email_clean)
    user_id = user.id if user else None

    password_hash = None
    if payload.purpose == "signup_2fa":
        existing_rec = db.get_otp_record(email_clean, payload.purpose)
        if existing_rec:
            password_hash = existing_rec.password_hash

    otp_code = db.create_otp_challenge(email_clean, purpose=payload.purpose, ttl_seconds=300, user_id=user_id, password_hash=password_hash)
    send_otp_email(email_clean, otp_code, purpose=payload.purpose)

    return {
        "status": "success",
        "message": "A new verification code has been sent to your email."
    }


@router.post("/logout")
@limiter.limit("15/minute")
def logout_user(request: Request, response: Response, session_token: Optional[str] = Cookie(None), db: DatabaseManager = Depends(get_db)):
    response.delete_cookie(key="session_token", path="/", secure=SESSION_COOKIE_SECURE, samesite="lax", httponly=True)
    response.delete_cookie(key="csrf_token", path="/", secure=SESSION_COOKIE_SECURE, samesite="lax")
    if session_token:
        db.session.query(DbSession).filter(DbSession.session_token == session_token).delete(synchronize_session=False)
        db._commit()
    return {"status": "success"}

@router.get("/me")
@limiter.limit("60/minute")
def get_me(request: Request, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
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
@limiter.limit("60/minute")
def ping_session(request: Request, user_id: int = Depends(get_current_user_id)):
    return {"status": "ok"}

@router.get("/config")
@limiter.limit("30/minute")
def get_auth_config(request: Request):
    from app.core import config
    return {
        "recaptcha_enabled": config.RECAPTCHA_ENABLED and bool(config.RECAPTCHA_SITE_KEY) and config.RECAPTCHA_SITE_KEY != "your_recaptcha_site_key_here",
        "recaptcha_site_key": config.RECAPTCHA_SITE_KEY if config.RECAPTCHA_SITE_KEY != "your_recaptcha_site_key_here" else ""
    }

