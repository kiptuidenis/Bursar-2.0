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
    daily_budget: Optional[int] = None
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

    @field_validator("daily_budget")
    @classmethod
    def validate_integer_daily_budget(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if not float(v).is_integer():
                raise ValueError("Daily budget must be a whole integer KES amount (no decimal places).")
            return int(v)
        return v

class DepositRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount to deposit must be a positive whole integer KES amount")

    @field_validator("amount")
    @classmethod
    def validate_integer_amount(cls, v: int) -> int:
        if not float(v).is_integer():
            raise ValueError("Deposit amount must be a whole positive integer KES amount (no decimal places).")
        return int(v)

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
    otp_code: Optional[str] = None

class StepUpOTPPayload(BaseModel):
    purpose: str = Field("payout_stepup", description="Purpose for step-up OTP challenge (e.g. payout_stepup, phone_update)")

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

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class DeactivateRequest(BaseModel):
    password: str
    confirmation: str

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



