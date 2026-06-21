import uuid
import httpx
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("bursar.intasend")

class IntasendClient:
    def __init__(self, secret_key: str, publishable_key: str, mode: str = "simulation"):
        self.secret_key = secret_key
        self.publishable_key = publishable_key
        self.mode = mode.lower()

    @property
    def base_url(self) -> str:
        if self.mode == "live":
            return "https://payment.intasend.com/api"
        return "https://sandbox.intasend.com/api"

    @property
    def headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.secret_key:
            headers["Authorization"] = f"Bearer {self.secret_key}"
        return headers

    async def initiate_stk_push(self, phone_number: str, amount: float, api_ref: str, 
                                 email: str = "user@bursar.co.ke") -> Dict[str, Any]:
        """Initiate M-Pesa STK Push collection."""
        if self.mode == "simulation":
            await asyncio.sleep(0.1)
            sim_id = f"sim_invoice_{uuid.uuid4().hex[:12]}"
            return {
                "invoice": {
                    "id": sim_id,
                    "invoice_id": sim_id,
                    "state": "PENDING",
                    "provider": "M-PESA",
                    "charges": "0.00",
                    "net_amount": amount,
                    "currency": "KES",
                    "value": str(amount),
                    "account": email,
                    "api_ref": api_ref
                }
            }

        # Format number to 254... format if starting with 0 or +
        phone = phone_number.strip().replace("+", "")
        if phone.startswith("0") and len(phone) == 10:
            phone = "254" + phone[1:]

        payload = {
            "amount": int(amount),
            "phone_number": phone,
            "email": email,
            "api_ref": api_ref,
            "currency": "KES"
        }

        url = f"{self.base_url}/v1/payment/mpesa-stk-push/"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def check_stk_status(self, invoice_id: str) -> Dict[str, Any]:
        """Check status of a payment collection invoice."""
        if self.mode == "simulation":
            await asyncio.sleep(0.1)
            return {
                "invoice": {
                    "id": invoice_id,
                    "invoice_id": invoice_id,
                    "state": "COMPLETE",
                    "provider": "M-PESA",
                    "charges": "0.00",
                    "net_amount": 10.0,
                    "currency": "KES",
                    "value": "10.00"
                }
            }

        payload = {
            "invoice_id": invoice_id
        }

        url = f"{self.base_url}/v1/payment/status/"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def send_b2c_payout(self, phone_number: str, amount: float, recipient_name: str, 
                               narrative: str = "Bursar Payout") -> Dict[str, Any]:
        """Send money to M-Pesa client (B2C payout)."""
        if self.mode == "simulation":
            await asyncio.sleep(0.1)
            return {
                "tracking_id": f"sim_tracking_{uuid.uuid4().hex[:12]}",
                "status": "Completed"
            }

        # Format phone to 254...
        phone = phone_number.strip().replace("+", "")
        if phone.startswith("0") and len(phone) == 10:
            phone = "254" + phone[1:]

        payload = {
            "currency": "KES",
            "provider": "MPESA-B2C",
            "transactions": [
                {
                    "name": recipient_name,
                    "account": phone,
                    "amount": int(amount),
                    "narrative": narrative
                }
            ],
            "requires_approval": "NO"
        }

        url = f"{self.base_url}/v1/send-money/initiate/"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            # The initiate response includes a tracking_id for the transaction
            return response.json()

    async def check_payout_status(self, tracking_id: str) -> Dict[str, Any]:
        """Check status of a payout disbursement."""
        if self.mode == "simulation":
            await asyncio.sleep(0.1)
            return {
                "tracking_id": tracking_id,
                "status": "Completed"
            }

        payload = {
            "tracking_id": tracking_id
        }

        url = f"{self.base_url}/v1/send-money/status/"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
