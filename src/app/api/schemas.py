from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

# Pydantic input models
class AuthPayload(BaseModel):
    phone_number: Optional[str] = Field(None, description="Safaricom phone number (e.g. 254712345678 or 0712345678)")
    email: Optional[str] = Field(None, description="Email address for authentication")
    password: str = Field(..., min_length=8, description="Strong password (minimum 8 characters with uppercase, lowercase, digit, and symbol)")
    recaptcha_token: Optional[str] = Field(None, description="Google reCAPTCHA token")

class AuthLoginPayload(BaseModel):
    phone_number: Optional[str] = Field(None, description="Safaricom phone number (e.g. 254712345678 or 0712345678)")
    email: Optional[str] = Field(None, description="Email address for authentication")
    password: str = Field(..., min_length=1, description="Password")
    recaptcha_token: Optional[str] = Field(None, description="Google reCAPTCHA token")

class EmailSignupPayload(BaseModel):
    email: str = Field(..., description="Email address for authentication")
    password: str = Field(..., min_length=8, description="Strong password (minimum 8 characters with uppercase, lowercase, digit, and symbol)")
    recaptcha_token: Optional[str] = Field(None, description="Google reCAPTCHA token")

class EmailLoginPayload(BaseModel):
    email: str = Field(..., description="Email address for authentication")
    password: str = Field(..., min_length=1, description="Password")
    recaptcha_token: Optional[str] = Field(None, description="Google reCAPTCHA token")

class OTPVerificationPayload(BaseModel):
    email: str = Field(..., description="Recipient email address")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit numeric OTP code")
    purpose: str = Field("login_2fa", description="Purpose of OTP challenge")

class OTPResendPayload(BaseModel):
    email: str = Field(..., description="Recipient email address")
    purpose: str = Field("login_2fa", description="Purpose of OTP challenge")


class SettingsUpdate(BaseModel):
    phone_number: Optional[str] = None
    payout_time: Optional[str] = None
    mode: Optional[str] = None
    mpesa_consumer_key: Optional[str] = None
    mpesa_consumer_secret: Optional[str] = None
    mpesa_shortcode: Optional[str] = None
    mpesa_initiator_name: Optional[str] = None
    mpesa_initiator_password: Optional[str] = None
    mpesa_b2c_result_url: Optional[str] = None
    mpesa_b2c_timeout_url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    password: Optional[str] = None
    otp_code: Optional[str] = Field(None, pattern=r"^[0-9]{6}$", description="6-digit Email OTP for phone update verification")

class DepositRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount to deposit must be a positive whole integer KES amount")
    phone_number: Optional[str] = Field(None, description="Optional Safaricom M-Pesa phone number (e.g. 0712345678 or 254712345678)")

    @field_validator("amount")
    @classmethod
    def validate_integer_amount(cls, v: int) -> int:
        if not float(v).is_integer():
            raise ValueError("Deposit amount must be a whole positive integer KES amount (no decimal places).")
        return int(v)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().replace(" ", "").replace("-", "")
        if not clean:
            return None
        if clean.startswith("+"):
            clean = clean[1:]
        if clean.startswith("0") and len(clean) == 10:
            clean = "254" + clean[1:]
        elif clean.startswith("7") and len(clean) == 9:
            clean = "254" + clean
        elif clean.startswith("1") and len(clean) == 9:
            clean = "254" + clean

        import re
        if not re.match(r"^254(7\d{8}|1\d{8})$", clean):
            raise ValueError("Invalid phone number format. Must be a valid Kenyan Safaricom mobile number (e.g. 0712345678 or 254712345678).")
        return clean


class BudgetItemPayload(BaseModel):
    category: str = Field(..., min_length=1, max_length=100, description="Budget category name")
    amount: int = Field(..., gt=0, description="Amount allocated to category must be greater than zero")

    @field_validator("amount")
    @classmethod
    def validate_integer_amount(cls, v: int) -> int:
        if not float(v).is_integer():
            raise ValueError("Budget allocation amount must be a whole positive integer KES amount (no decimal places).")
        return int(v)

class DraftBudgetItem(BaseModel):
    category: str = Field(..., min_length=1, max_length=100, description="Category name")
    amount: int = Field(..., gt=0, description="Allocation amount")

    @field_validator("amount")
    @classmethod
    def validate_integer_amount(cls, v: int) -> int:
        if not float(v).is_integer():
            raise ValueError("Budget allocation amount must be a whole positive integer KES amount (no decimal places).")
        return int(v)

class BudgetLockPayload(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    items: Optional[List[DraftBudgetItem]] = None
    payout_phone_number: Optional[str] = None
    password: Optional[str] = None
    otp_code: Optional[str] = Field(None, pattern=r"^[0-9]{6}$", description="6-digit Email OTP for payout step-up")

class StepUpOTPPayload(BaseModel):
    purpose: str = Field("payout_stepup", description="Purpose for step-up OTP challenge (e.g. payout_stepup, phone_update, wallet_withdrawal, password_change, email_change, account_deactivation)")
    amount: Optional[int] = Field(None, description="Optional withdrawal amount in whole KES to pre-validate before sending OTP")
    new_email: Optional[str] = Field(None, description="New email address when requesting OTP for email change")

class PayoutPhonePayload(BaseModel):
    payout_phone_number: str = Field(..., description="Safaricom phone number for M-Pesa payouts")
    password: str = Field(..., description="User account password for authorization")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit Email OTP code")

class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    theme: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    password: Optional[str] = None
    otp_code: Optional[str] = Field(None, pattern=r"^[0-9]{6}$", description="6-digit Email OTP for email change verification")

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class WithdrawRequest(BaseModel):
    amount: int = Field(..., ge=10, le=250000, description="Amount to withdraw in whole KES (min KES 10, max KES 250,000)")
    payout_phone_number: Optional[str] = Field(None, description="Optional Safaricom M-Pesa phone number (e.g. 0712345678 or 254712345678)")
    password: str = Field(..., min_length=1, description="Account password for 2FA authorization")
    otp_code: str = Field(..., pattern=r"^[0-9]{6}$", description="6-digit Email OTP code")

    @field_validator("amount")
    @classmethod
    def validate_integer_amount(cls, v: int) -> int:
        if not float(v).is_integer():
            raise ValueError("Withdrawal amount must be a whole positive integer KES amount (no decimal places).")
        return int(v)

    @field_validator("payout_phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().replace(" ", "").replace("-", "")
        if not clean:
            return None
        if clean.startswith("+"):
            clean = clean[1:]
        if clean.startswith("0") and len(clean) == 10:
            clean = "254" + clean[1:]
        elif clean.startswith("7") and len(clean) == 9:
            clean = "254" + clean
        elif clean.startswith("1") and len(clean) == 9:
            clean = "254" + clean

        import re
        if not re.match(r"^254(7\d{8}|1\d{8})$", clean):
            raise ValueError("Invalid phone number format. Must be a valid Kenyan Safaricom mobile number (e.g. 0712345678 or 254712345678).")
        return clean

class DeactivateRequest(BaseModel):
    password: str
    confirmation: str
    otp_code: str = Field(..., pattern=r"^[0-9]{6}$", description="6-digit authorization OTP code")

class AdminLoginPayload(BaseModel):
    email: str = Field(..., description="Administrator email address")
    password: str = Field(..., min_length=1, description="Administrator password")

class AdminUserUnlockPayload(BaseModel):
    reason: Optional[str] = Field("Admin manual account unlock", description="Reason for unlocking account")

class AdminUser2FATogglePayload(BaseModel):
    enabled: bool = Field(..., description="Enable (true) or disable (false) 2FA")
    reason: Optional[str] = Field("Admin 2FA state modification", description="Reason for changing 2FA state")

class AdminUserRevokeSessionsPayload(BaseModel):
    reason: Optional[str] = Field("Admin emergency session revocation", description="Reason for session revocation")

class AdminUserImpersonatePayload(BaseModel):
    reason: Optional[str] = Field("Customer support troubleshooting", description="Reason for impersonating user")

class AdminUserUpdatePayoutPhonePayload(BaseModel):
    phone_number: str = Field(..., description="New Safaricom phone number (e.g. 254712345678 or 0712345678)")
    reason: Optional[str] = Field("Admin manual phone correction", description="Reason for updating payout phone")

class AdminBalanceAdjustmentPayload(BaseModel):
    user_id: int = Field(..., description="Target customer user ID")
    amount: int = Field(..., gt=0, description="Positive integer amount to adjust in KES")
    adjustment_type: str = Field("CREDIT", description="'CREDIT' or 'DEBIT'")
    reason: str = Field(..., min_length=3, description="Mandatory audit explanation for financial modification")
    reference_id: Optional[str] = Field(None, description="External banking or M-Pesa transaction reference")

    @field_validator("adjustment_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in ("CREDIT", "DEBIT"):
            raise ValueError("Adjustment type must be either 'CREDIT' or 'DEBIT'")
        return upper

class AdminLockOverridePayload(BaseModel):
    reason: str = Field(..., min_length=3, description="Mandatory audit explanation for emergency lock override")

class AdminDepositManualSettlePayload(BaseModel):
    mpesa_receipt: str = Field(..., min_length=5, description="Safaricom M-Pesa transaction reference (e.g. QWE123RTY)")
    reason: str = Field(..., min_length=3, description="Mandatory audit justification for manual reconciliation")

class AdminPayoutRetryPayload(BaseModel):
    reason: Optional[str] = Field("Manual administrative B2C payout retry", description="Reason for retrying failed payout")

class AdminPayoutMarkSettledPayload(BaseModel):
    transaction_id: str = Field(..., min_length=5, description="External banking or M-Pesa B2C transaction ID")
    reason: str = Field(..., min_length=3, description="Mandatory audit justification for manual settlement")

class AdminStatusTogglePayload(BaseModel):
    is_active: bool = Field(..., description="Target active status (True = active, False = deactivated)")
    reason: str = Field(..., min_length=3, description="Mandatory audit justification for modifying admin status")

class AdminUserNotificationPayload(BaseModel):
    title: str = Field(..., min_length=2, max_length=200, description="Title of the in-app notification")
    message: str = Field(..., min_length=3, description="Body content of the notification")
    type: str = Field("INFO", description="Notification severity / style ('INFO', 'WARNING', 'SUCCESS', 'DANGER')")
    reason: Optional[str] = Field("Customer support notification", description="Audit justification for sending notification")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in ("INFO", "WARNING", "SUCCESS", "DANGER"):
            return "INFO"
        return upper

class AdminCreateAccountPayload(BaseModel):
    email: str = Field(..., min_length=5, description="Staff admin email address")
    password: str = Field(..., min_length=8, description="Strong password for admin account")
    role: str = Field(..., description="Role: 'superadmin', 'finops', 'support', 'auditor'")
    reason: Optional[str] = Field("Admin account provisioning", description="Audit justification")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean:
            raise ValueError("Invalid email format")
        return clean

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("superadmin", "finops", "support", "auditor"):
            raise ValueError("Role must be one of: superadmin, finops, support, auditor")
        return clean

class AdminRoleUpdatePayload(BaseModel):
    role: str = Field(..., description="New role: 'superadmin', 'finops', 'support', 'auditor'")
    reason: str = Field(..., min_length=3, description="Mandatory audit justification for role update")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("superadmin", "finops", "support", "auditor"):
            raise ValueError("Role must be one of: superadmin, finops, support, auditor")
        return clean








