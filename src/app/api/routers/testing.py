import os
import time
import secrets
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Body

from app.db.manager import DatabaseManager
from app.db.models import User, AdminUser, Payout
from app.api.dependencies import get_db, session_manager
from app.core.csrf import generate_csrf_token
from app.services.email import last_sent_otp_emails

router = APIRouter(prefix="/api/test", tags=["Testing"])


@router.post("/setup-session")
def setup_test_session(
    request: Request,
    response: Response,
    payload: dict = Body(default={}),
    db: DatabaseManager = Depends(get_db)
):
    if payload.get("user_id"):
        user_id = int(payload["user_id"])
    elif payload.get("legacy_phone_only"):
        phone = payload.get("phone_number") or f"2547{datetime.datetime.now().microsecond:06d}0"
        password = payload.get("password") or "Str0ng!P@ssw0rd2026!"
        user_id = db.create_user(phone, password)
    else:
        phone = payload.get("phone_number") or ("" if payload.get("email_only") else f"2547{datetime.datetime.now().microsecond:06d}0")
        email = payload.get("email") or f"user_{datetime.datetime.now().microsecond:06d}@example.com"
        password = payload.get("password") or "Str0ng!P@ssw0rd2026!"
        two_factor = payload.get("two_factor_enabled", False)
        pwd_hash, salt = db._hash_password(password)
        try:
            user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone, phone_number=phone if phone else None)
            user = db.session.query(User).filter(User.id == user_id).first()
            if user:
                user.two_factor_enabled = two_factor
                db._commit()
        except Exception:
            user = db.get_user_by_email(email)
            user_id = user.id if user else 1

    # Optionally seed wallet balance for E2E finance tests
    initial_balance = payload.get("balance", 0)
    if initial_balance and initial_balance > 0:
        db.adjust_balance(user_id, int(initial_balance))

    user_agent = request.headers.get("user-agent", "Unknown Device")
    ip_address = request.client.host if request.client else "127.0.0.1"
    token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db, user_agent=user_agent, ip_address=ip_address)

    # Set session and CSRF cookies
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400,
        path="/"
    )
    new_csrf = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=new_csrf,
        httponly=False,
        secure=False,
        samesite="lax",
        path="/"
    )
    return {"status": "success", "user_id": user_id, "session_token": token}


@router.post("/setup-admin-session")
def setup_test_admin_session(
    request: Request,
    response: Response,
    payload: dict = Body(default={}),
    db: DatabaseManager = Depends(get_db)
):
    email = payload.get("email") or f"admin_{datetime.datetime.now().microsecond:06d}@bursar.co.ke"
    password = payload.get("password") or "Admin!Pass2026Secure"
    role = payload.get("role") or "superadmin"
    pwd_hash, salt = db._hash_password(password)

    admin = db.get_admin_by_email(email)
    if not admin:
        admin_id = db.create_admin_user(email=email, password_hash=pwd_hash, salt=salt, role=role)
    else:
        admin_id = admin["id"]
        admin_obj = db.session.query(AdminUser).filter(AdminUser.id == admin_id).first()
        if admin_obj:
            admin_obj.role = role
            db._commit()

    user_agent = request.headers.get("user-agent", "Playwright Test")
    ip_address = request.client.host if request.client else "127.0.0.1"
    token = f"adm_{secrets.token_urlsafe(32)}"
    expires_at = int(time.time()) + 86400

    db.create_admin_session(
        admin_id=admin_id,
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at
    )

    response.set_cookie(
        key="admin_session_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400,
        path="/"
    )
    new_csrf = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=new_csrf,
        httponly=False,
        secure=False,
        samesite="lax",
        path="/"
    )
    db.create_admin_audit_log(
        admin_id=admin_id,
        action="ADMIN_LOGIN",
        target_type="AdminSession",
        target_id=admin_id,
        reason="Automated test admin session established",
        ip_address=ip_address
    )
    return {"status": "success", "admin_id": admin_id, "email": email, "role": role, "admin_session_token": token}


@router.post("/seed-audit-log")
def seed_test_audit_log(
    payload: dict = Body(default={}),
    db: DatabaseManager = Depends(get_db)
):
    admin_id = payload.get("admin_id", 1)
    action = payload.get("action", "ADMIN_FINANCIAL_ADJUSTMENT")
    target_type = payload.get("target_type", "User")
    target_id = payload.get("target_id", 1)
    before_state = payload.get("before_state", '{"balance": 1000}')
    after_state = payload.get("after_state", '{"balance": 5000}')
    reason = payload.get("reason", "Automated E2E compliance test log")
    ip_address = payload.get("ip_address", "127.0.0.1")

    log = db.create_admin_audit_log(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_state=before_state,
        after_state=after_state,
        reason=reason,
        ip_address=ip_address
    )
    return {"status": "success", "log_id": log}


@router.post("/seed-deposit")
def seed_test_deposit(
    payload: dict = Body(default={}),
    db: DatabaseManager = Depends(get_db)
):
    phone = payload.get("phone_number")
    email = payload.get("email")
    user_id = payload.get("user_id")

    if not user_id:
        if phone or email:
            phone = phone or f"2547{datetime.datetime.now().microsecond:06d}0"
            email = email or f"user_{phone}@example.com"
            user = db.get_user_by_email(email)
            if not user:
                pwd_hash, salt = db._hash_password("Str0ng!P@ssw0rd2026!")
                try:
                    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone, phone_number=phone)
                except Exception:
                    user = db.get_user_by_email(email)
                    user_id = user.id if user else 1
            else:
                user_id = user.id
        else:
            user_id = 1

    checkout_id = payload.get("checkout_request_id") or f"chk_test_{secrets.token_hex(6)}"
    amount = payload.get("amount", 2500)
    status = payload.get("status", "PENDING")
    mpesa_receipt = payload.get("mpesa_receipt")

    db.create_deposit(user_id=user_id, checkout_request_id=checkout_id, amount=amount)
    if status != "PENDING" or mpesa_receipt:
        db.update_deposit_status(checkout_request_id=checkout_id, status=status, mpesa_receipt=mpesa_receipt)

    return {
        "status": "success",
        "user_id": user_id,
        "checkout_request_id": checkout_id,
        "amount": amount,
        "deposit_status": status,
        "mpesa_receipt": mpesa_receipt
    }


@router.post("/seed-payout")
def seed_test_payout(
    payload: dict = Body(default={}),
    db: DatabaseManager = Depends(get_db)
):
    phone = payload.get("phone_number")
    email = payload.get("email")
    user_id = payload.get("user_id")

    if not user_id:
        if phone or email:
            phone = phone or f"2547{datetime.datetime.now().microsecond:06d}0"
            email = email or f"user_{phone}@example.com"
            user = db.get_user_by_email(email)
            if not user:
                pwd_hash, salt = db._hash_password("Str0ng!P@ssw0rd2026!")
                try:
                    user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone, phone_number=phone)
                except Exception:
                    user = db.get_user_by_email(email)
                    user_id = user.id if user else 1
            else:
                user_id = user.id
                phone = user.phone_number or phone
        else:
            user_id = 1
            phone = "254712345678"

    payout_date = payload.get("payout_date") or datetime.date.today().isoformat()
    amount = payload.get("amount", 1200)
    status = payload.get("status", "FAILED")
    conversation_id = payload.get("conversation_id") or f"AG_B2C_{secrets.token_hex(6)}"
    originator_id = payload.get("originator_conversation_id") or f"ORIG_{secrets.token_hex(4)}"
    transaction_id = payload.get("transaction_id", "")
    error_msg = payload.get("error_message", "")

    payout = Payout(
        user_id=user_id,
        payout_date=payout_date,
        amount=amount,
        phone_number=phone,
        status=status,
        conversation_id=conversation_id,
        originator_conversation_id=originator_id,
        transaction_id=transaction_id,
        error_message=error_msg
    )
    db.session.add(payout)
    db._commit()

    return {
        "status": "success",
        "payout_id": payout.id,
        "user_id": user_id,
        "amount": amount,
        "payout_status": status,
        "conversation_id": conversation_id,
        "transaction_id": transaction_id
    }


@router.get("/latest-otp")
def get_latest_test_otp(email: str = "", purpose: str = ""):
    email_clean = email.strip().lower()
    if email_clean and email_clean in last_sent_otp_emails:
        entry = last_sent_otp_emails[email_clean]
        return {"status": "success", "otp_code": entry["otp_code"], "purpose": entry["purpose"], "email": entry["email"]}
    if last_sent_otp_emails:
        last_entry = list(last_sent_otp_emails.values())[-1]
        return {"status": "success", "otp_code": last_entry["otp_code"], "purpose": last_entry["purpose"], "email": last_entry["email"]}
    raise HTTPException(status_code=404, detail="No mock OTP found in email delivery queue.")
