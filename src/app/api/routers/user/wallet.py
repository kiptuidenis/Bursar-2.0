import json
import secrets
import datetime
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.db.manager import DatabaseManager
from app.db.models import User, Wallet, Settings, Payout
from app.api.dependencies import get_db, get_current_user_id
from app.api.schemas import WithdrawRequest
from app.core.limiter import limiter
from app.services.payment_gateway import send_b2c_payout

logger = logging.getLogger("bursar.wallet")

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])

@router.post("/withdraw")
@limiter.limit("5/minute")
async def withdraw_funds(
    request: Request,
    payload: WithdrawRequest,
    user_id: int = Depends(get_current_user_id),
    db: DatabaseManager = Depends(get_db)
):
    """
    Secure cash-out withdrawal endpoint.
    Enforces pre-validation, deposit unlock checks, 2FA password & OTP authorization,
    idempotency protection, and pessimistic row locking to prevent double-spending.
    """
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if idempotency_key:
        cached = db.get_idempotency_record(user_id, idempotency_key, "/api/wallet/withdraw")
        if cached:
            return JSONResponse(
                status_code=cached["response_code"],
                content=json.loads(cached["response_body"])
            )

    user = db.session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # 1. Email Link & Verification Check
    if not user.email or not user.email_verified:
        raise HTTPException(
            status_code=400,
            detail="User account does not have a verified email address. Please link an email address in Profile first."
        )

    # 2. Deposit Lock Check (Disallow during active schedule)
    if db.is_deposit_locked(user_id):
        raise HTTPException(
            status_code=400,
            detail="Deposit balance is currently locked. Withdrawal is not permitted during an active schedule."
        )

    # 3. 2FA Password Check
    if not db._verify_password(payload.password, user.password_hash, user.salt):
        raise HTTPException(status_code=401, detail="Invalid password credential.")

    # 4. 2FA OTP Challenge Check
    is_valid_otp = db.verify_otp_challenge(user.email, payload.otp_code, purpose="wallet_withdrawal")
    if not is_valid_otp:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    # 5. Destination Phone Number Resolution
    payout_phone = payload.payout_phone_number or db.get_payout_phone_number(user_id)
    if not payout_phone:
        raise HTTPException(
            status_code=400,
            detail="A valid recipient Safaricom M-Pesa phone number is required."
        )

    # 6. Pessimistic Row Locking & Atomic Debit
    debited = db.debit_wallet_atomic(user_id, payload.amount)
    if not debited:
        wallet = db.get_user_wallet(user_id)
        avail = wallet.available_balance if wallet else 0
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance. (Available: KES {avail}, Required: KES {payload.amount})."
        )
    wallet = db.get_user_wallet(user_id)

    # 7. Gateway B2C Payout Dispatch
    user_settings = db.get_settings(user_id, decrypt_secrets=True)
    recipient_name = f"{user.first_name} {user.last_name}".strip() or "Bursar Customer"
    eat_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S")

    try:
        gateway_res = await send_b2c_payout(
            phone_number=payout_phone,
            amount=float(payload.amount),
            recipient_name=recipient_name,
            narrative="Wallet Cashout",
            user_settings=user_settings
        )

        response_code = gateway_res.get("ResponseCode", "")
        if response_code != "0":
            err_desc = gateway_res.get("ResponseDescription", "Unknown gateway error")
            raise Exception(f"Gateway rejected withdrawal: {err_desc} (Code: {response_code})")

    except Exception as e:
        # Gateway failure: atomically refund wallet balance
        logger.error(f"Withdrawal gateway dispatch failed for user {user_id}: {e}")
        db.adjust_balance(user_id, payload.amount)
        db.log_event(user_id, "ERROR", f"Wallet cash-out withdrawal of KES {payload.amount:.2f} failed: {str(e)}. Funds refunded.")
        raise HTTPException(
            status_code=502,
            detail=f"Payment gateway disbursement error: {str(e)}. Your wallet balance has been refunded."
        )

    # 8. Record Ledger Payout Transaction
    transaction_id = gateway_res.get("TransactionID") or gateway_res.get("ConversationID") or f"WD_{secrets.token_hex(4).upper()}"
    payout_date_key = f"WD_{datetime.date.today().strftime('%Y-%m-%d')}_{secrets.token_hex(3)}"
    
    payout = Payout(
        user_id=user_id,
        payout_date=payout_date_key,
        amount=payload.amount,
        phone_number=payout_phone,
        status="SUCCESS",
        transaction_id=transaction_id,
        conversation_id=gateway_res.get("ConversationID", ""),
        originator_conversation_id=gateway_res.get("OriginatorConversationID", ""),
        completed_at=eat_now
    )
    db.session.add(payout)
    db._commit()

    # 9. Audit Logging
    client_ip = request.client.host if request.client else "127.0.0.1"
    db.log_event(
        user_id,
        "INFO",
        f"Wallet cash-out withdrawal of KES {payload.amount:.2f} completed successfully to {payout_phone}. Receipt: {transaction_id}."
    )
    db.create_admin_audit_log(
        admin_id=None,
        action="USER_WALLET_WITHDRAWAL",
        target_type="User",
        target_id=user_id,
        reason=f"User initiated cash-out withdrawal of KES {payload.amount} to {payout_phone}",
        ip_address=client_ip
    )

    result_data = {
        "status": "success",
        "message": f"Successfully withdrawn KES {payload.amount} to {payout_phone}.",
        "amount": payload.amount,
        "balance": wallet.available_balance,
        "payout_phone": payout_phone,
        "transaction_id": transaction_id,
        "completed_at": eat_now
    }

    if idempotency_key:
        db.save_idempotency_record(
            user_id=user_id,
            key=idempotency_key,
            endpoint="/api/wallet/withdraw",
            response_code=200,
            response_body=json.dumps(result_data)
        )

    return result_data
