import os
from typing import Dict, Any, Optional
from app.services.mpesa import MpesaClient
from app.services.intasend import IntasendClient
from app.core.config import (
    PAYMENT_PROVIDER,
    MPESA_MODE, MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_LNM_SHORTCODE, MPESA_LNM_PASSKEY, MPESA_STK_CALLBACK_URL,
    MPESA_SHORTCODE, MPESA_INITIATOR_NAME, MPESA_INITIATOR_PASSWORD,
    INTASEND_MODE, INTASEND_SECRET_KEY, INTASEND_PUBLISHABLE_KEY
)

def get_gateway_provider(user_settings: dict) -> str:
    # Allow overriding provider via user settings dynamically, fallback to app global config
    provider = user_settings.get("payment_provider", PAYMENT_PROVIDER) or PAYMENT_PROVIDER
    return provider.lower().strip()

def create_mpesa_client(user_settings: dict) -> MpesaClient:
    user_mode = user_settings.get("mode", "sandbox")
    client_mode = "simulation" if user_mode == "simulation" else MPESA_MODE
    return MpesaClient(
        consumer_key=MPESA_CONSUMER_KEY,
        consumer_secret=MPESA_CONSUMER_SECRET,
        shortcode=MPESA_SHORTCODE,
        initiator_name=MPESA_INITIATOR_NAME,
        initiator_password=MPESA_INITIATOR_PASSWORD,
        mode=client_mode
    )

def create_intasend_client(user_settings: dict) -> IntasendClient:
    user_mode = user_settings.get("mode", "sandbox")
    client_mode = "simulation" if user_mode == "simulation" else INTASEND_MODE
    return IntasendClient(
        secret_key=INTASEND_SECRET_KEY,
        publishable_key=INTASEND_PUBLISHABLE_KEY,
        mode=client_mode
    )

async def initiate_stk_push(phone_number: str, amount: float, api_ref: str, user_settings: dict) -> Dict[str, Any]:
    """Routes and triggers STK Push deposit request using the active provider."""
    provider = get_gateway_provider(user_settings)
    if provider == "intasend":
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
    else:
        client = create_mpesa_client(user_settings)
        return await client.initiate_stk_push(
            phone_number=phone_number,
            amount=amount,
            callback_url=MPESA_STK_CALLBACK_URL,
            passkey=MPESA_LNM_PASSKEY,
            lnm_shortcode=MPESA_LNM_SHORTCODE
        )

async def check_stk_status(checkout_request_id: str, user_settings: dict) -> Dict[str, Any]:
    """Routes STK status check to active provider."""
    provider = get_gateway_provider(user_settings)
    if provider == "intasend":
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
    else:
        # Safaricom direct doesn't support immediate status lookup without OAuth token in basic client,
        # fallback to database status check (which receives asynchronous callback updates).
        return {
            "status": "PENDING",
            "invoice_id": checkout_request_id,
            "amount": 0.0
        }

async def send_b2c_payout(phone_number: str, amount: float, recipient_name: str, 
                          narrative: str, user_settings: dict, cert_bytes: Optional[bytes] = None) -> Dict[str, Any]:
    """Routes and triggers B2C disbursement/payout request using the active provider."""
    provider = get_gateway_provider(user_settings)
    if provider == "intasend":
        client = create_intasend_client(user_settings)
        res = await client.send_b2c_payout(
            phone_number=phone_number,
            amount=amount,
            recipient_name=recipient_name,
            narrative=narrative
        )
        tracking_id = res.get("tracking_id", "")
        status = res.get("status", "")
        return {
            "ResponseCode": "0" if status in ("Completed", "Processing", "Submitted") else "1",
            "ResponseDescription": status,
            "ConversationID": tracking_id,
            "OriginatorConversationID": tracking_id
        }
    else:
        client = create_mpesa_client(user_settings)
        from app.core.config import MPESA_B2C_RESULT_URL, MPESA_B2C_TIMEOUT_URL
        return await client.send_b2c_payout(
            phone_number=phone_number,
            amount=amount,
            result_url=MPESA_B2C_RESULT_URL,
            timeout_url=MPESA_B2C_TIMEOUT_URL,
            cert_bytes=cert_bytes
        )

async def check_payout_status(tracking_id: str, user_settings: dict) -> Dict[str, Any]:
    """Check status of a payout transaction."""
    provider = get_gateway_provider(user_settings)
    if provider == "intasend":
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
    else:
        return {
            "status": "PENDING",
            "tracking_id": tracking_id
        }
