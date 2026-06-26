import os
from typing import Optional, Generator
from fastapi import Depends, HTTPException, Cookie, Request
from app.db.manager import DatabaseManager
from app.core.security import SessionManager
from app.core.config import SECRET_KEY

raw_db_url = os.environ.get("DATABASE_URL", "bursar.db")
if raw_db_url.startswith("postgres://") or raw_db_url.startswith("postgresql://"):
    # Fallback to local SQLite file since SQLite cannot parse postgres URLs
    DB_FILE = "bursar.db"
else:
    DB_FILE = raw_db_url

db_manager = DatabaseManager(DB_FILE)
session_manager = SessionManager(secret_key=SECRET_KEY)

def get_db() -> Generator[DatabaseManager, None, None]:
    db = DatabaseManager(DB_FILE)
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
        
    return user_id
