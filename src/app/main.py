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

from app.api.dependencies import db_manager, get_db
from app.services.scheduler import BackgroundScheduler

# Import sub-routers
from app.api.routers import auth, settings, budget, deposits, payouts, callbacks, profile

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

app = FastAPI(lifespan=lifespan, title="Bursar 2.0 API")

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
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"}
    )

from app.core import config

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=config.CORS_ALLOWED_METHODS,
    allow_headers=config.CORS_ALLOWED_HEADERS,
    max_age=config.CORS_MAX_AGE,
)


# Register routers
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(profile.router)
app.include_router(budget.router)
app.include_router(deposits.router)
app.include_router(payouts.router)
app.include_router(callbacks.router)

@app.get("/api/diagnostics")
async def get_diagnostics():
    import subprocess
    try:
        commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        commit_hash = "unknown"
    return {
        "version": "1.2.0",
        "commit_hash": commit_hash,
        "timestamp": datetime.datetime.utcnow().isoformat()
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

# Mount static assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
