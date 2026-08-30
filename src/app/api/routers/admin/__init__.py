from app.api.routers.admin.auth import router as admin_auth_router
from app.api.routers.admin.overview import router as admin_overview_router
from app.api.routers.admin.users import router as admin_users_router
from app.api.routers.admin.finances import router as admin_finances_router
from app.api.routers.admin.deposits import router as admin_deposits_router
from app.api.routers.admin.payouts import router as admin_payouts_router
from app.api.routers.admin.audit import router as admin_audit_router
from app.api.routers.admin.system import router as admin_system_router

__all__ = [
    "admin_auth_router",
    "admin_overview_router",
    "admin_users_router",
    "admin_finances_router",
    "admin_deposits_router",
    "admin_payouts_router",
    "admin_audit_router",
    "admin_system_router"
]
