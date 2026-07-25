from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

# Pydantic input models
class AuthPayload(BaseModel):
    phone_number: str = Field(..., description="Safaricom phone number (e.g. 254712345678 or 0712345678)")
    password: str = Field(..., min_length=8, description="Strong password (minimum 8 characters with uppercase, lowercase, digit, and symbol)")
    recaptcha_token: Optional[str] = Field(None, description="Google reCAPTCHA token")

class AuthLoginPayload(BaseModel):
    phone_number: str = Field(..., description="Safaricom phone number (e.g. 254712345678 or 0712345678)")
    password: str = Field(..., min_length=1, description="Password")
    recaptcha_token: Optional[str] = Field(None, description="Google reCAPTCHA token")


class SettingsUpdate(BaseModel):
    balance: Optional[float] = None
    daily_budget: Optional[float] = None
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

class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to deposit must be greater than zero")

class BudgetItemPayload(BaseModel):
    category: str = Field(..., min_length=1, max_length=100, description="Budget category name")
    amount: float = Field(..., gt=0, description="Amount allocated to category must be greater than zero")

    @field_validator("amount")
    @classmethod
    def validate_integer_amount(cls, v: float) -> float:
        if not float(v).is_integer():
            raise ValueError("Budget allocation amount must be a whole positive integer (no decimal places).")
        return float(int(v))

class DraftBudgetItem(BaseModel):
    category: str = Field(..., min_length=1, max_length=100, description="Category name")
    amount: float = Field(..., gt=0, description="Allocation amount")

    @field_validator("amount")
    @classmethod
    def validate_integer_amount(cls, v: float) -> float:
        if not float(v).is_integer():
            raise ValueError("Budget allocation amount must be a whole positive integer (no decimal places).")
        return float(int(v))

class BudgetLockPayload(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    items: Optional[List[DraftBudgetItem]] = None

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

