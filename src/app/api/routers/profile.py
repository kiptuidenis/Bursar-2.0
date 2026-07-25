import re
import os
import time
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, UploadFile, File, Request

from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id, session_manager
from app.api.schemas import ProfileUpdate, PasswordChange, DeactivateRequest
from app.core.config import SESSION_COOKIE_SECURE

router = APIRouter(prefix="/api/profile", tags=["Profile"])



EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

@router.get("")
def get_profile(user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    profile = db.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    profile_dict = dict(profile)
    profile_dict["notifications_enabled"] = bool(profile_dict["notifications_enabled"])
    return profile_dict

from app.core.limiter import limiter

@router.post("")
@limiter.limit("10/minute")
def update_profile(request: Request, payload: ProfileUpdate, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No profile fields provided to update.")
        
    if "first_name" in updates and (updates["first_name"] is None or not updates["first_name"].strip()):
        raise HTTPException(status_code=400, detail="First name cannot be empty.")
    if "last_name" in updates and (updates["last_name"] is None or not updates["last_name"].strip()):
        raise HTTPException(status_code=400, detail="Last name cannot be empty.")
    if "email" in updates and (updates["email"] is None or not updates["email"].strip()):
        raise HTTPException(status_code=400, detail="Email address cannot be empty.")
        
    if "email" in updates and updates["email"]:
        if not re.match(EMAIL_REGEX, updates["email"]):
            raise HTTPException(status_code=400, detail="Invalid email address format.")
            
    db.update_profile(user_id, **updates)
    db.log_event(user_id, "INFO", "User profile details updated.")
    
    updated = db.get_profile(user_id)
    updated_dict = dict(updated) if updated else {}
    if "notifications_enabled" in updated_dict:
        updated_dict["notifications_enabled"] = bool(updated_dict["notifications_enabled"])
    return {"status": "success", "profile": updated_dict}

from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.limiter import limiter

@router.post("/password")
@limiter.limit("5/15minutes")
def change_password(request: Request, payload: PasswordChange, response: Response, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    profile = db.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found.")
        
    if not db.authenticate_user(profile["phone_number"], payload.current_password):
        raise HTTPException(status_code=401, detail="Incorrect current password.")
        
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password cannot be the same as your current password.")

    from app.core.password import validate_password_strength
    pwd_error = validate_password_strength(payload.new_password, user_context=profile["phone_number"])
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)
        
    db.update_password(user_id, payload.new_password)
    db.log_event(user_id, "INFO", "Password updated successfully.")
    
    from app.core.csrf import generate_csrf_token
    from app.core.config import SESSION_COOKIE_SECURE
    new_csrf = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=new_csrf,
        httponly=False,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/"
    )

    return {"status": "success"}

@router.get("/sessions")
def get_sessions(session_token: Optional[str] = Cookie(None), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    sessions = db.get_active_sessions(user_id)
    
    # Map raw session info to display details
    results = []
    for s in sessions:
        is_current = (s["session_token"] == session_token)
        
        # Simple OS / Browser parsing from User Agent
        ua = s["user_agent"]
        device = "Unknown Device"
        if "Windows" in ua:
            device = "Windows Desktop"
        elif "Macintosh" in ua:
            device = "macOS Desktop"
        elif "iPhone" in ua:
            device = "iPhone"
        elif "Android" in ua:
            device = "Android Device"
        elif "Linux" in ua:
            device = "Linux Desktop"
            
        browser = "Web Browser"
        if "Firefox" in ua:
            browser = "Firefox"
        elif "Chrome" in ua:
            browser = "Chrome"
        elif "Safari" in ua:
            browser = "Safari"
        elif "Edge" in ua:
            browser = "Edge"
            
        results.append({
            "id": s["id"],
            "device": f"{device} ({browser})",
            "ip_address": s["ip_address"],
            "created_at": s["created_at"],
            "is_current": is_current
        })
    return results

@router.delete("/sessions/other")
def revoke_other_sessions(session_token: Optional[str] = Cookie(None), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    if not session_token:
        raise HTTPException(status_code=401, detail="No active session found.")
    db.revoke_other_sessions(user_id, session_token)
    db.log_event(user_id, "INFO", "All other active sessions revoked.")
    return {"status": "success"}

@router.delete("/sessions/{session_id}")
def revoke_session(session_id: int, session_token: Optional[str] = Cookie(None), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    # Check if user is trying to revoke their current session
    sessions = db.get_active_sessions(user_id)
    target_session = next((s for s in sessions if s["id"] == session_id), None)
    if not target_session:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    if target_session["session_token"] == session_token:
        raise HTTPException(status_code=400, detail="Cannot revoke current session. Please log out instead.")
        
    db.revoke_session(user_id, session_id)
    db.log_event(user_id, "INFO", f"Active session (ID: {session_id}) revoked.")
    return {"status": "success"}

@router.post("/avatar")
def upload_avatar(file: UploadFile = File(...), user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    contents = file.file.read()
    
    from app.core.image_validator import process_and_sanitize_avatar
    try:
        sanitized_bytes, ext = process_and_sanitize_avatar(contents)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    static_uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "uploads", "avatars")
    os.makedirs(static_uploads_dir, exist_ok=True)
    
    # Path safety guard: delete previous custom avatar file if present
    profile = db.get_profile(user_id)
    if profile and profile.get("avatar_url"):
        old_url = profile["avatar_url"]
        if old_url and old_url.startswith("/uploads/avatars/"):
            old_filename = os.path.basename(old_url)
            old_filepath = os.path.realpath(os.path.join(static_uploads_dir, old_filename))
            base_dir = os.path.realpath(static_uploads_dir)
            if old_filepath.startswith(base_dir) and os.path.isfile(old_filepath):
                try:
                    os.remove(old_filepath)
                except Exception as clean_err:
                    logger.warning(f"Failed to clean up previous avatar {old_filepath}: {clean_err}")

    # Full 32-character UUID filename
    filename = f"{user_id}_{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(static_uploads_dir, filename)
    
    with open(filepath, "wb") as f:
        f.write(sanitized_bytes)
        
    url = f"/uploads/avatars/{filename}"
    db.update_profile(user_id, avatar_url=url)
    db.log_event(user_id, "INFO", "User avatar uploaded and sanitized successfully.")
    
    return {"status": "success", "avatar_url": url}

@router.post("/deactivate")
def deactivate_account(
    payload: DeactivateRequest, 
    response: Response,
    user_id: int = Depends(get_current_user_id), 
    db: DatabaseManager = Depends(get_db)
):
    if payload.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail="Confirmation phrase must be 'DELETE'.")
        
    profile = db.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found.")
        
    if not db.authenticate_user(profile["phone_number"], payload.password):
        raise HTTPException(status_code=401, detail="Incorrect password PIN.")
        
    settings = db.get_settings(user_id)
    if settings and settings.get("balance", 0.0) > 0.0:
        raise HTTPException(status_code=400, detail="Cannot deactivate account with a non-zero wallet balance. Please distribute or withdraw your remaining balance first.")
        
    db.deactivate_user(user_id)
    
    # Clean up session cookie
    response.delete_cookie(key="session_token", secure=SESSION_COOKIE_SECURE)
    return {"status": "success"}

