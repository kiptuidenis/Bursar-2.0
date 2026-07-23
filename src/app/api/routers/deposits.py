import uuid
from fastapi import APIRouter, Depends, HTTPException
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.api.schemas import DepositRequest
from app.services.payment_gateway import initiate_stk_push, check_stk_status

router = APIRouter(prefix="/api/deposit", tags=["Deposits"])

@router.post("/initiate")
async def initiate_deposit(payload: DepositRequest, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    amount = payload.amount
    if not amount.is_integer() or amount < 10 or amount > 250000:
        raise HTTPException(status_code=400, detail="Invalid Amount.")

    settings = db.get_settings(user_id)
    phone = settings.get("phone_number", "")
    if not phone:
        raise HTTPException(status_code=400, detail="Target phone number must be configured in settings before depositing.")
        
    daily_budget = settings.get("daily_budget", 0.0)
    balance = settings.get("balance", 0.0)
    if daily_budget > 0 and (balance + amount) < daily_budget:
        raise HTTPException(status_code=400, detail=f"Total balance after deposit (KES {balance + amount:.2f}) cannot be less than your daily budget (KES {daily_budget:.2f}).")


    api_ref = f"DEP_{uuid.uuid4().hex[:12]}"
    
    try:
        res = await initiate_stk_push(
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

@router.get("/status/{checkout_request_id}")
async def check_deposit_status(checkout_request_id: str, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    deposit = db.get_deposit(checkout_request_id)
    if not deposit or deposit["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Deposit transaction not found.")
        
    if deposit["status"] == "PENDING":
        settings = db.get_settings(user_id)
        try:
            gateway_res = await check_stk_status(checkout_request_id, dict(settings) if settings else {})
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                if db.update_deposit_status(checkout_request_id, "SUCCESS", "POLL_VERIFIED"):
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
