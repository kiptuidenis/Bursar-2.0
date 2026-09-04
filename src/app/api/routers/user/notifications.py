from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.manager import DatabaseManager
from app.api.dependencies import get_db, get_current_user_id
from app.core.limiter import limiter

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("")
@limiter.limit("60/minute")
def list_notifications(request: Request, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    notifications, unread_count = db.get_notifications(user_id)
    return {
        "status": "success",
        "unread_count": unread_count,
        "notifications": notifications
    }

@router.post("/{notification_id}/read")
@limiter.limit("60/minute")
def mark_notification_read(request: Request, notification_id: int, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    success = db.mark_notification_as_read(user_id, notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "message": "Notification marked as read"}

@router.post("/read-all")
@limiter.limit("30/minute")
def mark_all_notifications_read(request: Request, user_id: int = Depends(get_current_user_id), db: DatabaseManager = Depends(get_db)):
    db.mark_all_notifications_as_read(user_id)
    return {"status": "success", "message": "All notifications marked as read"}
