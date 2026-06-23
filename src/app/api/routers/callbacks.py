import uuid
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.services.payment_gateway import check_stk_status, check_payout_status

router = APIRouter(prefix="/api", tags=["Callbacks"])

@router.post("/callbacks/stk-callback")
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
                
        if db.update_deposit_status(checkout_request_id, "SUCCESS", receipt):
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

@router.post("/deposit/simulate-callback")
def simulate_stk_callback(payload: Dict[str, Any] = Body(...), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
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
        if db.update_deposit_status(checkout_request_id, "SUCCESS", receipt):
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

@router.post("/callbacks/b2c-result")
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
def mpesa_b2c_timeout_callback(body: Dict[str, Any] = Body(...), db: DatabaseManager = Depends(get_db)):
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
async def intasend_webhook(body: Dict[str, Any] = Body(...), db: DatabaseManager = Depends(get_db)):
    # Validate webhook challenge token if configured
    import os
    expected_challenge = os.environ.get("INTASEND_WEBHOOK_CHALLENGE")
    if expected_challenge:
        challenge = body.get("challenge")
        if challenge != expected_challenge:
            raise HTTPException(status_code=401, detail="Invalid webhook challenge token.")

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
                    # Deduct balance now that IntaSend has confirmed the disbursement
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
                    # Balance was never pre-deducted in the new flow — no refund needed
                    db.log_event(user_id, "ERROR", f"IntaSend payout failed (confirmed via webhook) for date {payout_date} at {failed_ts}. Tracking: {tracking_id}.")
        except Exception as e:
            db.log_event(user_id, "WARNING", f"Webhook double-check failed for payout tracking_id {tracking_id}: {str(e)}")
            
    return {"status": "acknowledged"}
