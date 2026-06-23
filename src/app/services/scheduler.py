import datetime
import os
import time
import threading
import sqlite3
import logging
from typing import Optional
from app.db.manager import DatabaseManager
from app.services.payment_gateway import send_b2c_payout

logger = logging.getLogger("bursar.scheduler")

async def check_and_trigger_payout(db: DatabaseManager, current_time: datetime.datetime, user_id: int, raise_exceptions: bool = False) -> bool:
    """
    Evaluates whether a payout is due for today for a specific user.
    If yes, updates database, deducts balance, and triggers B2C payout.
    """
    settings = db.get_settings(user_id)
    if not settings:
        if raise_exceptions:
            raise ValueError("User settings profile not found.")
        return False
        
    balance = settings.get("balance", 0.0)
    daily_budget = settings.get("daily_budget", 0.0)
    payout_time_str = settings.get("payout_time", "08:00")
    phone_number = settings.get("phone_number", "")
    mode = settings.get("mode", "simulation")
    
    # Check if budget is locked (payouts can only run if budget is finalized and locked)
    if not db.is_budget_locked(user_id, today=current_time.date()):
        if raise_exceptions:
            raise ValueError("Your daily budget must be locked before triggering a payout.")
        return False

    # 1. Check if daily budget is positive
    if daily_budget <= 0:
        if raise_exceptions:
            raise ValueError("Daily budget must be greater than zero to trigger a payout.")
        return False
        
    # Check start and end date bounds
    start_date_str = settings.get("start_date", "")
    end_date_str = settings.get("end_date", "")
    today_date_str = current_time.strftime("%Y-%m-%d")
    
    if start_date_str and today_date_str < start_date_str:
        if raise_exceptions:
            raise ValueError(f"Payout schedule has not started yet (Start Date: {start_date_str}).")
        return False
        
    if end_date_str and today_date_str > end_date_str:
        if raise_exceptions:
            raise ValueError(f"Payout schedule has already ended (End Date: {end_date_str}).")
        return False
        
    # 2. Check current time vs payout_time
    try:
        hour, minute = map(int, payout_time_str.split(":"))
    except ValueError:
        db.log_event(user_id, "ERROR", f"Invalid payout time configuration: {payout_time_str}")
        if raise_exceptions:
            raise ValueError(f"Invalid payout time configuration: {payout_time_str}")
        return False
        
    payout_time_today = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if current_time < payout_time_today:
        if raise_exceptions:
            raise ValueError(f"Scheduled payout time ({payout_time_str}) has not been reached yet today.")
        return False
        
    # 3. Check if a payout already exists for today's date for this user
    today_date = current_time.strftime("%Y-%m-%d")
    
    payouts = db.get_payouts(user_id, limit=50)
    for p in payouts:
        if p["payout_date"] == today_date and p["status"] in ("SUCCESS", "PENDING"):
            if raise_exceptions:
                raise ValueError("A payout has already been processed or is pending for today.")
            return False
            
    # 4. Check if phone number is set
    if not phone_number:
        db.log_event(user_id, "WARNING", f"Skipping payout for {today_date} because no phone number is configured.")
        if raise_exceptions:
            raise ValueError("No recipient phone number is configured in Settings.")
        return False
        
    # 5. Verify balance
    if balance < daily_budget:
        db.log_event(user_id, "ERROR", f"Payout for {today_date} skipped: Insufficient balance (Available: KES {balance:.2f}, Required: KES {daily_budget:.2f}).")
        if raise_exceptions:
            raise ValueError(f"Insufficient wallet balance. (Available: KES {balance:.2f}, Required: KES {daily_budget:.2f}).")
        return False

    # 6. Deduct balance first
    db.adjust_balance(user_id, -daily_budget)
    
    # 7. Create payout record (Composite unique constraint checks user_id + payout_date)
    payout_id = None
    try:
        payout_id = db.create_payout(
            user_id=user_id,
            payout_date=today_date,
            amount=daily_budget,
            phone_number=phone_number,
            status="PENDING",
            conversation_id="",
            originator_conversation_id=""
        )
    except sqlite3.IntegrityError:
        db.adjust_balance(user_id, daily_budget)
        db.log_event(user_id, "WARNING", f"Aborted duplicate payout insertion for {today_date}.")
        return False
    except Exception as e:
        db.adjust_balance(user_id, daily_budget)
        db.log_event(user_id, "ERROR", f"Database error creating payout: {str(e)}")
        return False

    # 8. Trigger payment via unified payment gateway
    db.log_event(user_id, "INFO", f"Initiating {mode} payout of KES {daily_budget:.2f} for date {today_date} to {phone_number}.")
    try:
        gateway_res = await send_b2c_payout(
            phone_number=phone_number,
            amount=daily_budget,
            recipient_name="Recipient",
            narrative=f"Bursar Payout {today_date}",
            user_settings=settings
        )

            
        response_code = gateway_res.get("ResponseCode", "")
        conversation_id = gateway_res.get("ConversationID", "")
        originator_conv_id = gateway_res.get("OriginatorConversationID", "")
        res_desc = gateway_res.get("ResponseDescription", "")
        
        if response_code == "0":
            if mode == "simulation" or res_desc == "Completed":
                status = "SUCCESS"
                db.log_event(user_id, "INFO", f"Payout of KES {daily_budget:.2f} completed successfully.")
            else:
                status = "PENDING"
                db.log_event(user_id, "INFO", f"Payout request accepted. ID: {conversation_id}.")
                
            # Update the payout record details
            conn = db.connection
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE payouts 
                SET status = ?, conversation_id = ?, originator_conversation_id = ? 
                WHERE id = ?
            """, (status, conversation_id, originator_conv_id, payout_id))
            conn.commit()
            
            return True
        else:
            description = gateway_res.get("ResponseDescription", "Unknown error")
            raise Exception(f"Payment Gateway Error: {description} (Code: {response_code})")
            
    except Exception as e:
        db.adjust_balance(user_id, daily_budget)
        error_msg = str(e)
        db.log_event(user_id, "ERROR", f"Payout failed for {today_date}: {error_msg}")
        
        conn = db.connection
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE payouts 
            SET status = 'FAILED', error_message = ? 
            WHERE id = ?
        """, (error_msg, payout_id))
        conn.commit()
        
        return False


class BackgroundScheduler:
    def __init__(self, db: DatabaseManager, interval_seconds: int = 60):
        self.db = db
        self.interval_seconds = interval_seconds
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        # Log to a system virtual user ID 0 (or just system logger)
        try:
            db = DatabaseManager(self.db.db_path)
            db.log_event(0, "INFO", "Background scheduler started successfully.")
            db.close()
        except Exception:
            pass

    def stop(self) -> None:
        self.is_running = False
        try:
            db = DatabaseManager(self.db.db_path)
            db.log_event(0, "INFO", "Background scheduler stop request received.")
            db.close()
        except Exception:
            pass

    def _loop(self) -> None:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.is_running:
            db = DatabaseManager(self.db.db_path)
            try:
                # Periodically clean up expired or inactive sessions (5 minutes timeout)
                db.cleanup_expired_sessions(inactivity_timeout_seconds=300)
                
                # Fetch all registered users and process payouts individually
                users = db.get_all_users()
                for user in users:
                    user_id = user["id"]
                    settings = db.get_settings(user_id)
                    if settings:
                        now = datetime.datetime.now()
                        loop.run_until_complete(check_and_trigger_payout(db, now, user_id=user_id))
            except Exception as e:
                # Standalone log writing check
                try:
                    db.log_event(0, "ERROR", f"Scheduler loop error: {str(e)}")
                except Exception:
                    pass
            finally:
                db.close()
            
            # Sleep in 1-second increments
            for _ in range(self.interval_seconds):
                if not self.is_running:
                    break
                time.sleep(1)
        
        loop.close()
