import os
from typing import Optional, Generator
from fastapi import Depends, HTTPException, Cookie, Request
from app.db.manager import DatabaseManager
from app.core.security import SessionManager
from app.core.config import SECRET_KEY, FALLBACK_SECRET_KEYS

DB_FILE = os.environ.get("DATABASE_URL", "bursar.db")

db_manager = DatabaseManager(DB_FILE)
session_manager = SessionManager(secret_key=SECRET_KEY, fallback_secret_keys=FALLBACK_SECRET_KEYS)


def get_db() -> Generator[DatabaseManager, None, None]:
    db_file = os.environ.get("DATABASE_URL", "bursar.db")
    db = DatabaseManager(db_file)
    try:
        yield db
    finally:
        db.close()

# Dependency for authenticating users via HTTP-only cookie sessions
def get_current_user_id(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    db: DatabaseManager = Depends(get_db)
) -> int:
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication session required. Please log in.")
        
    is_poll = request.headers.get("x-background-poll") == "true"
    user_id = session_manager.validate_session(session_token, db=db, is_poll=is_poll)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication session expired or invalid. Please log in again.")
        
    request.state.user_id = user_id
    return user_id


# Dependency for authenticating administrative users via HTTP-only cookie sessions
def get_current_admin_user(
    request: Request,
    admin_session_token: Optional[str] = Cookie(None),
    db: DatabaseManager = Depends(get_db)
) -> dict:
    if not admin_session_token:
        raise HTTPException(status_code=401, detail="Admin authentication session required. Please log in.")

    admin_id = db.verify_admin_session(admin_session_token, inactivity_timeout_seconds=900)
    if not admin_id:
        raise HTTPException(status_code=401, detail="Admin session expired or invalid. Please log in again.")

    admin = db.get_admin_by_id(admin_id)
    if not admin or not admin.get("is_active", True):
        raise HTTPException(status_code=401, detail="Admin account is inactive or disabled.")

    request.state.admin = admin
    request.state.admin_id = admin["id"]
    return admin


def require_admin_roles(allowed_roles: list) -> callable:
    """Dependency factory enforcing Role-Based Access Control (RBAC) across administrative endpoints."""
    def role_checker(admin: dict = Depends(get_current_admin_user)) -> dict:
        role = admin.get("role", "")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access forbidden: requires one of the following roles: {', '.join(allowed_roles)}"
            )
        return admin
    return role_checker

