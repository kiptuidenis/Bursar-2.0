from app.api.routers.user.auth import router as user_auth_router, sanitize_phone_number
from app.api.routers.user.settings import router as user_settings_router
from app.api.routers.user.profile import router as user_profile_router
from app.api.routers.user.budget import router as user_budget_router
from app.api.routers.user.deposits import router as user_deposits_router
from app.api.routers.user.payouts import router as user_payouts_router
from app.api.routers.user.callbacks import router as user_callbacks_router
from app.api.routers.user.notifications import router as user_notifications_router
from app.api.routers.user.wallet import router as user_wallet_router

from app.api.routers.user import (
    auth,
    settings,
    profile,
    budget,
    deposits,
    payouts,
    callbacks,
    notifications,
    wallet
)

__all__ = [
    "user_auth_router",
    "user_settings_router",
    "user_profile_router",
    "user_budget_router",
    "user_deposits_router",
    "user_payouts_router",
    "user_callbacks_router",
    "user_notifications_router",
    "user_wallet_router",
    "sanitize_phone_number",
    "auth",
    "settings",
    "profile",
    "budget",
    "deposits",
    "payouts",
    "callbacks",
    "notifications",
    "wallet",
]
