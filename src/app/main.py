import os
import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import db_manager, get_db
from app.services.scheduler import BackgroundScheduler

# Import sub-routers
from app.api.routers import auth, settings, budget, deposits, payouts, callbacks, profile

# Lifespan context manager for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_manager.initialize()
    
    if "PYTEST_CURRENT_TEST" not in os.environ:
        app.state.scheduler = BackgroundScheduler(db_manager, interval_seconds=60)
        app.state.scheduler.start()
    else:
        app.state.scheduler = None
        
    yield
    
    if app.state.scheduler:
        app.state.scheduler.stop()
    db_manager.close()

app = FastAPI(lifespan=lifespan, title="Bursar 2.0 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
def get_dashboard_page():
    from fastapi.responses import FileResponse
    dashboard_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    raise HTTPException(status_code=404, detail="Dashboard not found")

# Mount static assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
