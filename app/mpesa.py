import base64
import uuid
import httpx
import asyncio
from typing import Dict, Any, Optional
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding

class MpesaClient:
    def __init__(self, consumer_key: str, consumer_secret: str, shortcode: str, 
                 initiator_name: str, initiator_password: str, mode: str = "simulation"):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.shortcode = shortcode
        self.initiator_name = initiator_name
        self.initiator_password = initiator_password
        self.mode = mode.lower()

    @property
    def base_url(self) -> str:
        if self.mode == "live":
            return "https://api.safaricom.co.ke"
        return "https://sandbox.safaricom.co.ke"

    async def get_access_token(self) -> str:
        """Generate OAuth 2.0 access token using credentials."""
        if not self.consumer_key or not self.consumer_secret:
            raise ValueError("Consumer key and secret are required for real API calls.")
            
        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        headers = {
            "Authorization": f"Basic {encoded_credentials}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["access_token"]

    def encrypt_password(self, cert_bytes: bytes) -> str:
        """Encrypt the initiator password using Safaricom's public certificate (DER format)."""
        if not self.initiator_password:
            raise ValueError("Initiator password is not configured.")
        if not cert_bytes:
            raise ValueError("Certificate bytes are required for password encryption.")
            
        # Load DER certificate
        cert = x509.load_der_x509_certificate(cert_bytes)
        public_key = cert.public_key()
        
        # Encrypt using PKCS1 v1.5 padding (Safaricom requirement)
        password_bytes = self.initiator_password.encode("utf-8")
        encrypted_bytes = public_key.encrypt(
            password_bytes,
            padding.PKCS1v15()
        )
        
        # Base64 encode the result
        return base64.b64encode(encrypted_bytes).decode("utf-8")

    async def send_b2c_payout(self, phone_number: str, amount: float, 
                              result_url: str, timeout_url: str, 
                              cert_bytes: Optional[bytes] = None) -> Dict[str, Any]:
        """Initiate a Business-to-Customer (B2C) payout."""
        if self.mode == "simulation":
            await asyncio.sleep(0.1)  # Simulate network latency
            return {
                "ConversationID": f"sim_conv_{uuid.uuid4().hex[:12]}",
                "OriginatorConversationID": f"sim_orig_{uuid.uuid4().hex[:12]}",
                "ResponseCode": "0",
                "ResponseDescription": "Accept the service request successfully."
            }

        # Validate that cert_bytes is provided for non-simulated mode
        if not cert_bytes:
            raise ValueError("Public certificate bytes (DER) are required for sandbox/live B2C payouts.")

        token = await self.get_access_token()
        encrypted_password = self.encrypt_password(cert_bytes)
        
        url = f"{self.base_url}/mpesa/b2c/v1/paymentrequest"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "InitiatorName": self.initiator_name,
            "SecurityCredential": encrypted_password,
            "CommandID": "BusinessPayment",
            "Amount": amount,
            "PartyA": self.shortcode,
            "PartyB": phone_number,
            "Remarks": "Bursar Daily Budget Payout",
            "QueueTimeOutURL": timeout_url,
            "ResultURL": result_url,
            "Occasion": "BursarPayout"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    async def initiate_stk_push(self, phone_number: str, amount: float, 
                                 callback_url: str, passkey: str, 
                                 lnm_shortcode: str) -> Dict[str, Any]:
        """Initiate Lipa Na M-Pesa Online STK Push request."""
        if self.mode == "simulation":
            await asyncio.sleep(0.1)
            return {
                "ResponseCode": "0",
                "ResponseDescription": "Success. Request accepted for processing",
                "MerchantRequestID": f"sim_merch_{uuid.uuid4().hex[:12]}",
                "CheckoutRequestID": f"sim_check_{uuid.uuid4().hex[:12]}",
                "CustomerMessage": "Success"
            }

        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        password_str = f"{lnm_shortcode}{passkey}{timestamp}"
        password = base64.b64encode(password_str.encode("utf-8")).decode("utf-8")

        token = await self.get_access_token()
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Format number to 254... format if starting with 0 or +
        phone = phone_number.strip().replace("+", "")
        if phone.startswith("0") and len(phone) == 10:
            phone = "254" + phone[1:]

        payload = {
            "BusinessShortCode": lnm_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": lnm_shortcode,
            "PhoneNumber": phone,
            "CallBackURL": callback_url,
            "AccountReference": "BursarWallet",
            "TransactionDesc": "Deposit"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
