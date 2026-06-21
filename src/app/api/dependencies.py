import os
from typing import Optional
from fastapi import Depends, HTTPException, Cookie
from app.db.manager import DatabaseManager
from app.core.security import SessionManager

DB_FILE = "bursar.db"
db_manager = DatabaseManager(DB_FILE)
session_manager = SessionManager()

def get_db() -> DatabaseManager:
    return db_manager

# Dependency for authenticating users via HTTP-only cookie sessions
def get_current_user_id(
    session_token: Optional[str] = Cookie(None),
    db: DatabaseManager = Depends(get_db)
) -> int:
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentication session required. Please log in.")
        
    user_id = session_manager.validate_session(session_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication session expired or invalid. Please log in again.")
        
    return user_id
