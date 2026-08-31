import os
import sys
import datetime

# Trigger configuration loading early
from app.core.config import load_dotenv
load_dotenv(".env")

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import db_manager, get_db, get_current_user_id
from app.db.manager import DatabaseManager
from app.services.scheduler import BackgroundScheduler
from app.core import config

# Import sub-routers
from app.api.routers import auth, settings, budget, deposits, payouts, callbacks, profile, notifications
from app.api.routers.admin import (
    admin_auth_router, admin_overview_router, admin_users_router,
    admin_finances_router, admin_deposits_router, admin_payouts_router,
    admin_audit_router, admin_system_router
)

# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # In test mode, delete old test DB file to ensure clean database state
    db_file = os.environ.get("DATABASE_URL", "bursar.db")
    if os.environ.get("DATABASE_URL") == "bursar_test.db" and os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass
            
    # Verify database accessibility and initialize schema (skip connection check in unit tests)
    if "PYTEST_CURRENT_TEST" not in os.environ:
        import sqlalchemy
        import logging
        logger = logging.getLogger("bursar.startup")
        try:
            # 1. Verify connection first
            with db_manager.engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            # 2. Then initialize database schema/tables
            db_manager.initialize()
        except Exception as e:
            db_uri = db_manager.db_path
            try:
                from sqlalchemy.engine.url import make_url
                parsed_url = make_url(db_uri)
                if parsed_url.password:
                    db_uri = parsed_url.render_as_string(hide_password=True)
            except Exception:
                pass
            logger.critical(f"Database connection verification failed for {db_uri}! Error: {e}")
            raise RuntimeError(
                f"The database at {db_uri} is not accessible or connection was refused. "
                f"Please verify your connection settings, credentials, network routes, and security groups. Error: {e}"
            ) from e
    else:
        db_manager.initialize()
            
    if "PYTEST_CURRENT_TEST" not in os.environ and os.environ.get("DISABLE_SCHEDULER") != "1":
        app.state.scheduler = BackgroundScheduler(db_manager, interval_seconds=60)
        app.state.scheduler.start()
    else:
        app.state.scheduler = None
        
    yield
    
    if app.state.scheduler:
        app.state.scheduler.stop()
    db_manager.close()

docs_url = "/docs" if config.SHOW_API_DOCS else None
redoc_url = "/redoc" if config.SHOW_API_DOCS else None
openapi_url = "/openapi.json" if config.SHOW_API_DOCS else None

app = FastAPI(
    lifespan=lifespan,
    title="Bursar 2.0 API",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url
)

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    import logging
    logger = logging.getLogger("bursar.api")
    
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()}
        )
        
    logger.error(f"Unhandled Exception: {str(exc)}\n{traceback.format_exc()}")
    # Never leak raw python/SQL exception strings to clients
    detail_msg = "An internal server error occurred. Please try again later."
    return JSONResponse(
        status_code=500,
        content={"detail": detail_msg}
    )

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core import config
from app.core.limiter import limiter

@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    response = JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts. Please try again later."}
    )
    response.headers["Retry-After"] = "60"
    return response

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=config.CORS_ALLOWED_METHODS,
    allow_headers=config.CORS_ALLOWED_HEADERS,
    max_age=config.CORS_MAX_AGE,
)

from app.core.csrf import CSRFProtectionMiddleware
app.add_middleware(CSRFProtectionMiddleware)

from app.core.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

from starlette.middleware.trustedhost import TrustedHostMiddleware
if "*" not in config.ALLOWED_HOSTS or not (config.IS_DEV_MODE or config.IS_TEST_MODE):
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)


# Register routers
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(profile.router)
app.include_router(budget.router)
app.include_router(deposits.router)
app.include_router(payouts.router)
app.include_router(callbacks.router)
app.include_router(notifications.router)
app.include_router(admin_auth_router)
app.include_router(admin_overview_router)
app.include_router(admin_users_router)
app.include_router(admin_finances_router)
app.include_router(admin_deposits_router)
app.include_router(admin_payouts_router)
app.include_router(admin_audit_router)
app.include_router(admin_system_router)

if config.IS_TEST_MODE:
    from fastapi import Body, Response
    @app.post("/api/test/setup-session")
    def setup_test_session(request: Request, response: Response, payload: dict = Body(default={}), db: DatabaseManager = Depends(get_db)):
        from app.api.dependencies import session_manager
        
        if payload.get("user_id"):
            user_id = int(payload["user_id"])
        else:
            phone = payload.get("phone_number") or ("" if payload.get("email_only") else f"2547{datetime.datetime.now().microsecond:06d}0")
            email = payload.get("email") or f"user_{datetime.datetime.now().microsecond:06d}@example.com"
            password = payload.get("password") or "Str0ng!P@ssw0rd2026!"
            two_factor = payload.get("two_factor_enabled", False)
            pwd_hash, salt = db._hash_password(password)
            try:
                user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone, phone_number=phone if phone else None)
                user = db.session.query(User).filter(User.id == user_id).first()
                if user:
                    user.two_factor_enabled = two_factor
                    db._commit()
            except Exception:
                user = db.get_user_by_email(email)
                user_id = user.id if user else 1
            
        # Optionally seed wallet balance for E2E finance tests
        initial_balance = payload.get("balance", 0)
        if initial_balance and initial_balance > 0:
            db.adjust_balance(user_id, int(initial_balance))

        user_agent = request.headers.get("user-agent", "Unknown Device")
        ip_address = request.client.host if request.client else "127.0.0.1"
        token = session_manager.create_session(user_id, expires_in_seconds=86400, db=db, user_agent=user_agent, ip_address=ip_address)
        
        # Set session and CSRF cookies
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=86400,
            path="/"
        )
        from app.core.csrf import generate_csrf_token
        new_csrf = generate_csrf_token()
        response.set_cookie(
            key="csrf_token",
            value=new_csrf,
            httponly=False,
            secure=False,
            samesite="lax",
            path="/"
        )
        return {"status": "success", "user_id": user_id, "session_token": token}

    @app.post("/api/test/setup-admin-session")
    def setup_test_admin_session(request: Request, response: Response, payload: dict = Body(default={}), db: DatabaseManager = Depends(get_db)):
        import time
        import secrets
        email = payload.get("email") or f"admin_{datetime.datetime.now().microsecond:06d}@bursar.co.ke"
        password = payload.get("password") or "Admin!Pass2026Secure"
        role = payload.get("role") or "superadmin"
        pwd_hash, salt = db._hash_password(password)
        
        admin = db.get_admin_by_email(email)
        if not admin:
            admin_id = db.create_admin_user(email=email, password_hash=pwd_hash, salt=salt, role=role)
        else:
            admin_id = admin["id"]
            from app.db.models import AdminUser
            admin_obj = db.session.query(AdminUser).filter(AdminUser.id == admin_id).first()
            if admin_obj:
                admin_obj.role = role
                db._commit()
            
        user_agent = request.headers.get("user-agent", "Playwright Test")
        ip_address = request.client.host if request.client else "127.0.0.1"
        token = f"adm_{secrets.token_urlsafe(32)}"
        expires_at = int(time.time()) + 86400
        
        db.create_admin_session(
            admin_id=admin_id,
            token=token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        
        response.set_cookie(
            key="admin_session_token",
            value=token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=86400,
            path="/"
        )
        from app.core.csrf import generate_csrf_token
        new_csrf = generate_csrf_token()
        response.set_cookie(
            key="csrf_token",
            value=new_csrf,
            httponly=False,
            secure=False,
            samesite="lax",
            path="/"
        )
        db.create_admin_audit_log(
            admin_id=admin_id,
            action="ADMIN_LOGIN",
            target_type="AdminSession",
            target_id=admin_id,
            reason="Automated test admin session established",
            ip_address=ip_address
        )
        return {"status": "success", "admin_id": admin_id, "email": email, "role": role, "admin_session_token": token}

    @app.post("/api/test/seed-audit-log")
    def seed_test_audit_log(payload: dict = Body(default={}), db: DatabaseManager = Depends(get_db)):
        admin_id = payload.get("admin_id", 1)
        action = payload.get("action", "ADMIN_FINANCIAL_ADJUSTMENT")
        target_type = payload.get("target_type", "User")
        target_id = payload.get("target_id", 1)
        before_state = payload.get("before_state", '{"balance": 1000}')
        after_state = payload.get("after_state", '{"balance": 5000}')
        reason = payload.get("reason", "Automated E2E compliance test log")
        ip_address = payload.get("ip_address", "127.0.0.1")

        log = db.create_admin_audit_log(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
            ip_address=ip_address
        )
        return {"status": "success", "log_id": log}

    @app.post("/api/test/seed-deposit")
    def seed_test_deposit(payload: dict = Body(default={}), db: DatabaseManager = Depends(get_db)):
        import secrets
        phone = payload.get("phone_number")
        email = payload.get("email")
        user_id = payload.get("user_id")
        
        if not user_id:
            if phone or email:
                phone = phone or f"2547{datetime.datetime.now().microsecond:06d}0"
                email = email or f"user_{phone}@example.com"
                user = db.get_user_by_email(email)
                if not user:
                    pwd_hash, salt = db._hash_password("Str0ng!P@ssw0rd2026!")
                    try:
                        user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone, phone_number=phone)
                    except Exception:
                        user = db.get_user_by_email(email)
                        user_id = user.id if user else 1
                else:
                    user_id = user.id
            else:
                user_id = 1

        checkout_id = payload.get("checkout_request_id") or f"chk_test_{secrets.token_hex(6)}"
        amount = payload.get("amount", 2500)
        status = payload.get("status", "PENDING")
        mpesa_receipt = payload.get("mpesa_receipt")
        
        db.create_deposit(user_id=user_id, checkout_request_id=checkout_id, amount=amount)
        if status != "PENDING" or mpesa_receipt:
            db.update_deposit_status(checkout_request_id=checkout_id, status=status, mpesa_receipt=mpesa_receipt)
            
        return {
            "status": "success",
            "user_id": user_id,
            "checkout_request_id": checkout_id,
            "amount": amount,
            "deposit_status": status,
            "mpesa_receipt": mpesa_receipt
        }

    @app.post("/api/test/seed-payout")
    def seed_test_payout(payload: dict = Body(default={}), db: DatabaseManager = Depends(get_db)):
        import secrets
        phone = payload.get("phone_number")
        email = payload.get("email")
        user_id = payload.get("user_id")
        
        if not user_id:
            if phone or email:
                phone = phone or f"2547{datetime.datetime.now().microsecond:06d}0"
                email = email or f"user_{phone}@example.com"
                user = db.get_user_by_email(email)
                if not user:
                    pwd_hash, salt = db._hash_password("Str0ng!P@ssw0rd2026!")
                    try:
                        user_id = db.create_user_email(email, pwd_hash, salt, payout_phone=phone, phone_number=phone)
                    except Exception:
                        user = db.get_user_by_email(email)
                        user_id = user.id if user else 1
                else:
                    user_id = user.id
                    phone = user.phone_number or phone
            else:
                user_id = 1
                phone = "254712345678"

        payout_date = payload.get("payout_date") or datetime.date.today().isoformat()
        amount = payload.get("amount", 1200)
        status = payload.get("status", "FAILED")
        conversation_id = payload.get("conversation_id") or f"AG_B2C_{secrets.token_hex(6)}"
        originator_id = payload.get("originator_conversation_id") or f"ORIG_{secrets.token_hex(4)}"
        transaction_id = payload.get("transaction_id", "")
        error_msg = payload.get("error_message", "")
        
        from app.db.models import Payout
        payout = Payout(
            user_id=user_id,
            payout_date=payout_date,
            amount=amount,
            phone_number=phone,
            status=status,
            conversation_id=conversation_id,
            originator_conversation_id=originator_id,
            transaction_id=transaction_id,
            error_message=error_msg
        )
        db.session.add(payout)
        db._commit()
        
        return {
            "status": "success",
            "payout_id": payout.id,
            "user_id": user_id,
            "amount": amount,
            "payout_status": status,
            "conversation_id": conversation_id,
            "transaction_id": transaction_id
        }



@app.get("/api/diagnostics")
@limiter.limit("10/minute")
async def get_diagnostics(request: Request, user_id: int = Depends(get_current_user_id)):
    return {
        "status": "healthy",
        "version": config.APP_VERSION,
        "commit_hash": config.COMMIT_HASH,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

@app.get("/dashboard")
def get_dashboard_page(request: Request, db = Depends(get_db)):
    from fastapi.responses import FileResponse, RedirectResponse
    
    session_token = request.cookies.get("session_token")
    if not session_token:
        return RedirectResponse(url="/#login", status_code=302)
        
    from app.api.dependencies import session_manager
    user_id = session_manager.validate_session(session_token, db=db, is_poll=False)
    if not user_id:
        response = RedirectResponse(url="/#login", status_code=302)
        response.delete_cookie("session_token")
        return response
        
    dashboard_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    if os.path.exists(dashboard_path):
        response = FileResponse(dashboard_path)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    raise HTTPException(status_code=404, detail="Dashboard not found")

@app.get("/admin")
def get_admin_page(request: Request):
    from fastapi.responses import FileResponse
    admin_path = os.path.join(os.path.dirname(__file__), "static", "admin.html")
    if os.path.exists(admin_path):
        response = FileResponse(admin_path)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    raise HTTPException(status_code=404, detail="Admin portal page not found")

# Mount static assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

