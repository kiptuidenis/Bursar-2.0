import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, UniqueConstraint, Text, Boolean, BigInteger
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(50), unique=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    two_factor_enabled = Column(Boolean, default=True, nullable=False)
    payout_phone_number = Column(String(50), default="")
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    first_name = Column(String(100), default="")
    last_name = Column(String(100), default="")
    avatar_url = Column(String(255), default="")
    bio = Column(String(500), default="")
    theme = Column(String(50), default="")
    notifications_enabled = Column(Integer, default=1)
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(String(50), default="")
    
    # Relationships
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    budget = relationship("Budget", back_populates="user", uselist=False, cascade="all, delete-orphan")
    settings = relationship("Settings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    payouts = relationship("Payout", back_populates="user", cascade="all, delete-orphan")
    logs = relationship("Log", back_populates="user", cascade="all, delete-orphan")
    budget_items = relationship("BudgetItem", back_populates="user", cascade="all, delete-orphan")
    deposits = relationship("Deposit", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    otp_codes = relationship("OtpCode", back_populates="user", cascade="all, delete-orphan")

class Wallet(Base):
    __tablename__ = "wallets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    available_balance = Column(BigInteger, default=0, nullable=False) # Whole KES
    locked_balance = Column(BigInteger, default=0, nullable=False)    # Whole KES
    currency = Column(String(3), default="KES", nullable=False)
    
    user = relationship("User", back_populates="wallet")

class Budget(Base):
    __tablename__ = "budgets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    daily_budget = Column(BigInteger, default=0, nullable=False)       # Whole KES
    payout_time = Column(String(10), default="08:00", nullable=False)
    start_date = Column(String(10), default="", nullable=False)
    end_date = Column(String(10), default="", nullable=False)
    locked_until = Column(String(50), default="", nullable=False)
    
    user = relationship("User", back_populates="budget")

class OtpCode(Base):
    __tablename__ = "otp_codes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    otp_code_hash = Column(String(255), nullable=False)
    purpose = Column(String(50), nullable=False)
    expires_at = Column(String(50), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(String(50), nullable=False)
    password_hash = Column(Text, nullable=True)

    user = relationship("User", back_populates="otp_codes")

class Settings(Base):
    __tablename__ = "settings"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance = Column(Integer, default=0)
    daily_budget = Column(Integer, default=0)
    phone_number = Column(String(50), default="")
    payout_time = Column(String(10), default="08:00")
    mode = Column(String(50), default="sandbox")
    mpesa_consumer_key = Column(String(255), default="")
    mpesa_consumer_secret = Column(String(255), default="")
    mpesa_shortcode = Column(String(50), default="")
    mpesa_initiator_name = Column(String(100), default="")
    mpesa_initiator_password = Column(String(255), default="")
    mpesa_b2c_result_url = Column(String(255), default="")
    mpesa_b2c_timeout_url = Column(String(255), default="")
    budget_locked_until = Column(String(50), default="")
    deposit_locked_until = Column(String(50), default="")
    start_date = Column(String(50), default="")
    end_date = Column(String(50), default="")
    
    user = relationship("User", back_populates="settings")

class Payout(Base):
    __tablename__ = "payouts"
    __table_args__ = (
        UniqueConstraint("user_id", "payout_date", name="uq_user_payout_date"),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    payout_date = Column(String(50), nullable=False)
    amount = Column(Integer, nullable=False)
    phone_number = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    conversation_id = Column(String(100), default="")
    originator_conversation_id = Column(String(100), default="")
    transaction_id = Column(String(100), default="")
    error_message = Column(String(500), default="")
    completed_at = Column(String(50), default="")
    failed_at = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="payouts")

class Log(Base):
    __tablename__ = "logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level = Column(String(20), nullable=False)
    message = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="logs")

class BudgetItem(Base):
    __tablename__ = "budget_items"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_category"),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(100), nullable=False)
    amount = Column(Integer, nullable=False)
    
    user = relationship("User", back_populates="budget_items")

class Deposit(Base):
    __tablename__ = "deposits"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    checkout_request_id = Column(String(100), unique=True, nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False)
    mpesa_receipt = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="deposits")

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "key", "endpoint", name="uq_user_idemp_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    endpoint = Column(String(128), nullable=False)
    response_code = Column(Integer, nullable=False)
    response_body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False)
    user_agent = Column(String(255), default="")
    ip_address = Column(String(100), default="")
    expires_at = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_activity = Column(Integer)
    
    user = relationship("User", back_populates="sessions")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="INFO", nullable=False)  # "INFO", "WARNING", "SUCCESS", "DANGER"
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="notifications")
