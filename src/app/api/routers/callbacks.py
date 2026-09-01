import uuid
import hmac
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.services.payment_gateway import check_stk_status, check_payout_status
from app.core import config
from app.core.limiter import limiter

router = APIRouter(prefix="/api", tags=["Callbacks"])


def verify_callback_authenticity(request: Request, body: Dict[str, Any] = None) -> bool:
    """
    Validates callback signature authenticity using SHA-256 HMAC signature or secret token verification.
    Always fails closed (raises 401 Unauthorized) if authentication check fails or signature is missing.
    """
    # 1. IP Whitelisting Check (if configured)
    if config.ALLOWED_CALLBACK_IPS and request.client:
        client_ip = request.client.host
        if client_ip not in config.ALLOWED_CALLBACK_IPS:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized callback request: IP address is not permitted."
            )

    # 2. Check X-IntaSend-Signature header HMAC verification
    signature = request.headers.get("X-IntaSend-Signature", "").strip()
    secret_key = config.INTASEND_WEBHOOK_CHALLENGE or config.CALLBACK_SECRET_TOKEN

    if signature:
        if not secret_key:
            raise HTTPException(status_code=401, detail="Unauthorized callback request: Webhook secret key not configured.")
        
        import json
        import hashlib
        try:
            body_dict = body if isinstance(body, dict) else {}
            body_bytes = json.dumps(body_dict, separators=(',', ':')).encode("utf-8")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid request body.")

        expected_sig = hmac.new(
            secret_key.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature.encode("utf-8"), expected_sig.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Unauthorized callback request: Signature verification failed.")

        return True

    # 3. Check direct token in headers, query parameters, or body challenge
    query_token = request.query_params.get("token", "").strip()
    header_token = (
        request.headers.get("X-Callback-Secret", "")
        or request.headers.get("X-Webhook-Token", "")
    ).strip()

    body_dict = body if isinstance(body, dict) else {}
    body_challenge = str(body_dict.get("challenge", "") or "").strip()

    provided_tokens = [t for t in (query_token, header_token, body_challenge) if t]
    expected_tokens = []
    if config.CALLBACK_SECRET_TOKEN:
        expected_tokens.append(config.CALLBACK_SECRET_TOKEN)
    if config.INTASEND_WEBHOOK_CHALLENGE:
        expected_tokens.append(config.INTASEND_WEBHOOK_CHALLENGE)
    if config.IS_TEST_MODE:
        expected_tokens.append("testnet")

    if not provided_tokens:
        raise HTTPException(status_code=401, detail="Unauthorized callback request: Missing signature header or token.")

    token_valid = False
    for provided in provided_tokens:
        for expected in expected_tokens:
            if hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
                token_valid = True
                break
        if token_valid:
            break

    if not token_valid:
        raise HTTPException(status_code=401, detail="Unauthorized callback request: Invalid secret token.")

    return True


@router.post("/callbacks/stk-callback")
@limiter.limit("60/minute")
async def mpesa_stk_callback(
    request: Request,
    body: Dict[str, Any] = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    verify_callback_authenticity(request, body)

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
        # Active Gateway Double-Check before crediting balance
        settings = db.get_settings(user_id)
        try:
            gateway_res = await check_stk_status(checkout_request_id, dict(settings) if settings else {})
            verified_status = gateway_res.get("status", "PENDING")
            if verified_status != "SUCCESS" and not config.IS_TEST_MODE:
                db.log_event(user_id, "WARNING", f"STK Push callback double-check unverified for deposit {checkout_request_id}. Status: {verified_status}")
                return {"status": "unverified"}
        except Exception as e:
            if not config.IS_TEST_MODE:
                db.log_event(user_id, "WARNING", f"STK Push callback verification failed for {checkout_request_id}: {str(e)}")
                return {"status": "unverified"}

        # Get Mpesa Receipt Number
        receipt = ""
        meta_items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
        for item in meta_items:
            if item.get("Name") == "MpesaReceiptNumber":
                receipt = item.get("Value", "")
                break
                
        if db.update_deposit_status(checkout_request_id, "SUCCESS", receipt):
            db.adjust_balance(user_id, amount)
            db.log_event(user_id, "INFO", f"STK Push deposit of KES {amount:.2f} completed successfully. Receipt: {receipt}.")
            
            # Auto-lock budget & deposit if user has budget categories or schedule configured
            items = db.get_budget_items(user_id)
            settings = db.get_settings(user_id, decrypt_secrets=False)
            has_schedule = bool(settings.get("end_date"))
            if items or has_schedule:
                db.lock_deposit(user_id)
                db.lock_budget(user_id)
                db.log_event(user_id, "INFO", "Budget automatically locked due to active deposit.")
    else:
        db.update_deposit_status(checkout_request_id, "FAILED")
        db.log_event(user_id, "ERROR", f"STK Push deposit failed. Reason: {result_desc}.")
        
    return {"status": "acknowledged"}


@router.post("/deposit/simulate-callback")
def simulate_stk_callback(
    payload: Dict[str, Any] = Body(...),
    user_id: int = Depends(get_current_user_id),
    db: DatabaseManager = Depends(get_db)
):
    # Simulation route is disabled in production environment
    if not config.IS_DEV_MODE and not config.IS_TEST_MODE:
        raise HTTPException(
            status_code=403,
            detail="Simulated callbacks are disabled in production environment."
        )

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
        if db.update_deposit_status(checkout_request_id, "SUCCESS", receipt):
            db.adjust_balance(user_id, amount)
            db.log_event(user_id, "INFO", f"[SIMULATED] STK Push deposit of KES {amount:.2f} completed successfully. Receipt: {receipt}.")
            
            items = db.get_budget_items(user_id)
            settings = db.get_settings(user_id, decrypt_secrets=False)
            has_schedule = bool(settings.get("end_date"))
            if items or has_schedule:
                db.lock_deposit(user_id)
                db.lock_budget(user_id)
                db.log_event(user_id, "INFO", "Budget automatically locked due to simulated active deposit.")
    else:
        db.update_deposit_status(checkout_request_id, "FAILED")
        db.log_event(user_id, "ERROR", f"[SIMULATED] STK Push deposit failed.")
        
    return {"status": "success"}


@router.post("/callbacks/b2c-result")
@limiter.limit("60/minute")
async def mpesa_b2c_result_callback(
    request: Request,
    body: Dict[str, Any] = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    verify_callback_authenticity(request, body)

    result = body.get("Result")
    if not result:
        return {"status": "ignored"}
        
    conversation_id = result.get("ConversationID", "")
    result_code = result.get("ResultCode")
    result_desc = result.get("ResultDesc", "")
    transaction_id = result.get("TransactionID", "")
    
    matching_payout = db.get_payout_by_conversation_id(conversation_id)
    if not matching_payout or matching_payout["status"] != "PENDING":
        return {"status": "ignored"}
        
    user_id = matching_payout["user_id"]
    payout_amount = matching_payout["amount"]
    payout_date = matching_payout["payout_date"]
    
    if result_code == 0:
        if db.update_payout_status(
            conversation_id=conversation_id,
            status="SUCCESS",
            transaction_id=transaction_id,
            error_message=""
        ):
            db.log_event(user_id, "INFO", f"M-Pesa B2C payout of KES {payout_amount:.2f} for date {payout_date} was completed successfully. Receipt: {transaction_id}.")
    else:
        if db.update_payout_status(
            conversation_id=conversation_id,
            status="FAILED",
            transaction_id="",
            error_message=result_desc
        ):
            db.adjust_balance(user_id, payout_amount)
            db.log_event(user_id, "ERROR", f"M-Pesa B2C payout failed for date {payout_date}. Reason: {result_desc}. KES {payout_amount:.2f} refunded.")
        
    return {"status": "acknowledged"}


@router.post("/callbacks/b2c-timeout")
@limiter.limit("60/minute")
async def mpesa_b2c_timeout_callback(
    request: Request,
    body: Dict[str, Any] = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    verify_callback_authenticity(request, body)

    conversation_id = body.get("ConversationID", "")
    result_desc = body.get("ResultDesc", "Transaction timed out at Safaricom Queue.")
    
    matching_payout = db.get_payout_by_conversation_id(conversation_id)
    if not matching_payout or matching_payout["status"] != "PENDING":
        return {"status": "ignored"}
        
    user_id = matching_payout["user_id"]
    payout_amount = matching_payout["amount"]
    payout_date = matching_payout["payout_date"]
    
    if db.update_payout_status(
        conversation_id=conversation_id,
        status="FAILED",
        transaction_id="",
        error_message=result_desc
    ):
        db.adjust_balance(user_id, payout_amount)
        db.log_event(user_id, "ERROR", f"M-Pesa B2C payout timed out for date {payout_date}. Reason: {result_desc}. KES {payout_amount:.2f} refunded.")
    
    return {"status": "acknowledged"}


@router.post("/callbacks/intasend-webhook")
@limiter.limit("60/minute")
async def intasend_webhook(
    request: Request,
    body: Dict[str, Any] = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    verify_callback_authenticity(request, body)

    invoice_id = body.get("invoice_id")
    tracking_id = body.get("tracking_id")
    
    if invoice_id:
        deposit = db.get_deposit(invoice_id)
        if not deposit or deposit["status"] != "PENDING":
            return {"status": "ignored"}
            
        user_id = deposit["user_id"]
        amount = deposit["amount"]
        
        settings = db.get_settings(user_id)
        try:
            gateway_res = await check_stk_status(invoice_id, dict(settings) if settings else {})
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                if db.update_deposit_status(invoice_id, "SUCCESS", "WEBHOOK_VERIFIED"):
                    db.adjust_balance(user_id, amount)
                    db.log_event(user_id, "INFO", f"IntaSend deposit of KES {amount:.2f} completed successfully (verified). Invoice: {invoice_id}.")
                    
                    items = db.get_budget_items(user_id)
                    settings = db.get_settings(user_id, decrypt_secrets=False)
                    has_schedule = bool(settings.get("end_date"))
                    if items or has_schedule:
                        db.lock_deposit(user_id)
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

        import datetime as _dt
        eat_now = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=3))).replace(tzinfo=None)

        settings = db.get_settings(user_id)
        try:
            gateway_res = await check_payout_status(tracking_id, dict(settings) if settings else {})
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                completed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")
                if db.update_payout_status(
                    conversation_id=tracking_id,
                    status="SUCCESS",
                    transaction_id=tracking_id,
                    error_message="",
                    completed_at=completed_ts
                ):
                    db.adjust_balance(user_id, -payout_amount)
                    db.log_event(user_id, "INFO", f"IntaSend payout of KES {payout_amount:.2f} for date {payout_date} confirmed successfully at {completed_ts}. Tracking: {tracking_id}.")
            elif status == "FAILED":
                failed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")
                if db.update_payout_status(
                    conversation_id=tracking_id,
                    status="FAILED",
                    transaction_id="",
                    error_message="IntaSend disbursement failed",
                    failed_at=failed_ts
                ):
                    db.log_event(user_id, "ERROR", f"IntaSend payout failed (confirmed via webhook) for date {payout_date} at {failed_ts}. Tracking: {tracking_id}.")
        except Exception as e:
            db.log_event(user_id, "WARNING", f"Webhook double-check failed for payout tracking_id {tracking_id}: {str(e)}")
            
    return {"status": "acknowledged"}
