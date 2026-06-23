import os
from typing import Dict, Any, Optional
from app.services.intasend import IntasendClient
from app.core.config import (
    INTASEND_MODE, INTASEND_SECRET_KEY, INTASEND_PUBLISHABLE_KEY
)

# For compatibility with legacy test mock setups referencing PAYMENT_PROVIDER
PAYMENT_PROVIDER = "intasend"

def create_intasend_client(user_settings: dict) -> IntasendClient:
    user_mode = user_settings.get("mode", "sandbox").lower()
    client_mode = "simulation" if user_mode == "simulation" else INTASEND_MODE
    return IntasendClient(
        secret_key=INTASEND_SECRET_KEY,
        publishable_key=INTASEND_PUBLISHABLE_KEY,
        mode=client_mode
    )

async def initiate_stk_push(phone_number: str, amount: float, api_ref: str, user_settings: dict) -> Dict[str, Any]:
    """Triggers STK Push deposit request using IntaSend."""
    client = create_intasend_client(user_settings)
    res = await client.initiate_stk_push(
        phone_number=phone_number,
        amount=amount,
        api_ref=api_ref
    )
    invoice = res.get("invoice", {})
    return {
        "ResponseCode": "0" if invoice.get("state") == "PENDING" else "1",
        "ResponseDescription": invoice.get("state", "PENDING"),
        "CheckoutRequestID": invoice.get("invoice_id") or invoice.get("id")
    }

async def check_stk_status(checkout_request_id: str, user_settings: dict) -> Dict[str, Any]:
    """Checks STK status using IntaSend."""
    client = create_intasend_client(user_settings)
    res = await client.check_stk_status(checkout_request_id)
    invoice = res.get("invoice", {})
    state = invoice.get("state", "").upper()
    
    status = "PENDING"
    if state == "COMPLETE":
        status = "SUCCESS"
    elif state == "FAILED":
        status = "FAILED"
        
    return {
        "status": status,
        "invoice_id": checkout_request_id,
        "amount": invoice.get("net_amount")
    }

async def send_b2c_payout(phone_number: str, amount: float, recipient_name: str, 
                          narrative: str, user_settings: dict, cert_bytes: Optional[bytes] = None) -> Dict[str, Any]:
    """Triggers B2C disbursement/payout request using IntaSend."""
    client = create_intasend_client(user_settings)
    res = await client.send_b2c_payout(
        phone_number=phone_number,
        amount=amount,
        recipient_name=recipient_name,
        narrative=narrative
    )
    tracking_id = res.get("tracking_id", "")
    status = res.get("status", "")
    # IntaSend B2C valid in-progress/success states — all map to accepted (Code 0)
    accepted_statuses = ("Completed", "Processing", "Submitted", "Confirming balance", "Sending", "Queued")
    return {
        "ResponseCode": "0" if status in accepted_statuses else "1",
        "ResponseDescription": status,
        "ConversationID": tracking_id,
        "OriginatorConversationID": tracking_id
    }

async def check_payout_status(tracking_id: str, user_settings: dict) -> Dict[str, Any]:
    """Checks status of a payout transaction using IntaSend."""
    client = create_intasend_client(user_settings)
    res = await client.check_payout_status(tracking_id)
    status = res.get("status", "")
    
    status_upper = status.upper()
    mapped_status = "PENDING"
    if status_upper in ("COMPLETED", "COMPLETE", "SUCCESS"):
        mapped_status = "SUCCESS"
    elif status_upper in ("FAILED", "REJECTED"):
        mapped_status = "FAILED"
        
    return {
        "status": mapped_status,
        "tracking_id": tracking_id
    }
