import datetime
import os
import time
import threading
import sqlalchemy
from app.db.models import Payout, Deposit
import logging
from typing import Optional
from app.db.manager import DatabaseManager
from app.services.payment_gateway import send_b2c_payout, check_stk_status, check_payout_status

logger = logging.getLogger("bursar.scheduler")

async def check_and_trigger_payout(db: DatabaseManager, current_time: datetime.datetime, user_id: int, raise_exceptions: bool = False) -> bool:
    """
    Evaluates whether a payout is due for today for a specific user.
    If yes, updates database, deducts balance, and triggers B2C payout.
    """
    settings = db.get_settings(user_id, decrypt_secrets=True)
    if not settings:
        if raise_exceptions:
            raise ValueError("User settings profile not found.")
        return False
        
    balance = int(settings.get("balance", 0))
    daily_budget = int(settings.get("daily_budget", 0))
    payout_time_str = settings.get("payout_time", "08:00")
    phone_number = settings.get("phone_number", "")
    mode = settings.get("mode", "simulation")
    
    # 1. Check start and end date bounds
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

    # 2. Check if budget is locked (payouts can only run if budget is finalized and locked)
    if not db.is_budget_locked(user_id, today=current_time.date()):
        if raise_exceptions:
            raise ValueError("Your daily budget must be locked before triggering a payout.")
        return False

    # 3. Check if daily budget is positive
    if daily_budget <= 0:
        if raise_exceptions:
            raise ValueError("Daily budget must be greater than zero to trigger a payout.")
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
        
    # 5. Verify balance (must have enough BEFORE initiating — we check first, deduct only after success)
    if balance < daily_budget:
        db.log_event(user_id, "ERROR", f"Payout for {today_date} skipped: Insufficient balance (Available: KES {balance}, Required: KES {daily_budget}).")
        
        # Auto-create in-app notification if an unread warning doesn't exist
        notifications, _ = db.get_notifications(user_id)
        has_unread_warning = any(not n["is_read"] and n["type"] == "WARNING" for n in notifications)
        if not has_unread_warning:
            db.create_notification(
                user_id=user_id,
                title="Payout Skipped — Low Balance",
                message=f"Your daily payout of KES {daily_budget} was skipped because your wallet balance (KES {balance}) is insufficient. Please deposit funds to resume automated payouts.",
                notif_type="WARNING"
            )

        if raise_exceptions:
            raise ValueError(f"Insufficient wallet balance. (Available: KES {balance}, Required: KES {daily_budget}).")
        return False

    # 6. Find or prepare the payout record
    #    - If a FAILED record already exists for today (prior failed attempt), reset it for retry
    #    - Otherwise create a fresh PENDING record
    #    - This PENDING record acts as the duplicate-date lock guard via UNIQUE (user_id, payout_date)
    payout_id = None
    existing = db.get_payout_by_user_date(user_id, today_date)
    if existing and existing["status"] == "FAILED":
        payout_id = existing["id"]
        db.reset_failed_payout_for_retry(payout_id)
        db.log_event(user_id, "INFO", f"Retrying previously failed payout for {today_date}.")
    elif existing is None:
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
        except sqlalchemy.exc.IntegrityError:
            # Race condition: another process inserted between our check and create
            db.log_event(user_id, "WARNING", f"Aborted duplicate payout insertion for {today_date}.")
            if raise_exceptions:
                raise ValueError("A payout has already been processed or is pending for today.")
            return False
        except Exception as e:
            db.log_event(user_id, "ERROR", f"Database error creating payout: {str(e)}")
            if raise_exceptions:
                raise ValueError(f"Database error creating payout record: {str(e)}")
            return False
    else:
        # Record exists with SUCCESS or PENDING — already handled above in check step 3
        if raise_exceptions:
            raise ValueError("A payout has already been processed or is pending for today.")
        return False

    # 7. Trigger payment via IntaSend — balance is NOT deducted yet
    eat_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
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
                # Synchronous success — deduct balance immediately and stamp completed_at
                db.adjust_balance(user_id, -daily_budget)
                completed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")
                db.log_event(user_id, "INFO", f"Payout of KES {daily_budget:.2f} completed successfully at {completed_ts}.")
                payout = db.session.query(Payout).filter(Payout.id == payout_id).first()
                if payout:
                    payout.status = 'SUCCESS'
                    payout.conversation_id = conversation_id
                    payout.originator_conversation_id = originator_conv_id
                    payout.completed_at = completed_ts
                    db._commit()
            else:
                # Asynchronous (PENDING) — balance deducted when IntaSend webhook confirms
                db.log_event(user_id, "INFO", f"Payout request accepted by IntaSend. Tracking ID: {conversation_id}. Awaiting confirmation.")
                payout = db.session.query(Payout).filter(Payout.id == payout_id).first()
                if payout:
                    payout.status = 'PENDING'
                    payout.conversation_id = conversation_id
                    payout.originator_conversation_id = originator_conv_id
                    db._commit()

            return True
        else:
            description = gateway_res.get("ResponseDescription", "Unknown error")
            raise Exception(f"Payment Gateway Error: {description} (Code: {response_code})")

    except Exception as e:
        # Gateway call failed — balance was never deducted, so no refund needed
        error_msg = str(e)
        failed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")
        db.log_event(user_id, "ERROR", f"Payout failed for {today_date} at {failed_ts}: {error_msg}")

        payout = db.session.query(Payout).filter(Payout.id == payout_id).first()
        if payout:
            payout.status = 'FAILED'
            payout.error_message = error_msg
            payout.failed_at = failed_ts
            db._commit()

        if raise_exceptions:
            raise ValueError(f"Payout failed: {error_msg}")
        return False



async def process_daily_payouts_batch(db: DatabaseManager) -> dict:
    """Manually process daily payouts batch across all eligible registered users."""
    users = db.get_all_users()
    processed = 0
    succeeded = 0
    failed = 0
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
    for user in users:
        user_id = user["id"]
        try:
            res = await check_and_trigger_payout(db, now, user_id=user_id)
            processed += 1
            if res:
                succeeded += 1
        except Exception as e:
            logger.warning(f"Batch payout processing failed for user {user_id}: {e}")
            failed += 1
    return {"processed": processed, "succeeded": succeeded, "failed": failed}



async def poll_pending_deposits(db: DatabaseManager) -> None:
    """
    Polls IntaSend for all PENDING deposit transactions older than 30 seconds.
    Resolves them as SUCCESS or leaves them PENDING based on gateway response.
    This is the fallback for when IntaSend webhooks cannot reach the server (e.g. local dev).
    """
    cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(seconds=30)
    pending_records = db.session.query(Deposit).filter(
        Deposit.status == 'PENDING',
        Deposit.created_at <= cutoff_dt
    ).all()
    pending = [
        {"checkout_request_id": d.checkout_request_id, "user_id": d.user_id, "amount": d.amount}
        for d in pending_records
    ]

    for deposit in pending:
        checkout_request_id = deposit["checkout_request_id"]
        user_id = deposit["user_id"]
        amount = deposit["amount"]
        settings = db.get_settings(user_id)
        if not settings:
            continue
        try:
            gateway_res = await check_stk_status(checkout_request_id, dict(settings))
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                if db.update_deposit_status(checkout_request_id, "SUCCESS", "POLL_VERIFIED"):
                    db.adjust_balance(user_id, amount)
                    db.log_event(user_id, "INFO", f"[Scheduler Poll] Deposit {checkout_request_id} verified as SUCCESS. KES {amount:.2f} credited.")
                    db.lock_deposit(user_id)
                    items = db.get_budget_items(user_id)
                    if items:
                        db.lock_budget(user_id)
                        db.log_event(user_id, "INFO", "Budget automatically locked due to confirmed deposit.")
            elif status == "FAILED":
                db.update_deposit_status(checkout_request_id, "FAILED", "POLL_FAILED")
                db.log_event(user_id, "WARNING", f"[Scheduler Poll] Deposit {checkout_request_id} confirmed FAILED by gateway.")
        except Exception as e:
            logger.warning(f"Deposit poll error for {checkout_request_id}: {e}")


async def poll_pending_payouts(db: DatabaseManager) -> None:
    """
    Polls IntaSend for all PENDING payout transactions that have a conversation_id
    and are older than 30 seconds. Resolves them as SUCCESS or FAILED.
    This is the fallback for when IntaSend webhooks cannot reach the server (e.g. local dev).
    """
    cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(seconds=30)
    pending_records = db.session.query(Payout).filter(
        Payout.status == 'PENDING',
        Payout.conversation_id != '',
        Payout.created_at <= cutoff_dt
    ).all()
    pending = [
        {
            "id": p.id,
            "user_id": p.user_id,
            "amount": p.amount,
            "payout_date": p.payout_date,
            "conversation_id": p.conversation_id
        }
        for p in pending_records
    ]

    eat_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)

    for payout in pending:
        tracking_id = payout["conversation_id"]
        user_id = payout["user_id"]
        payout_amount = payout["amount"]
        payout_date = payout["payout_date"]
        settings = db.get_settings(user_id)
        if not settings:
            continue
        try:
            gateway_res = await check_payout_status(tracking_id, dict(settings))
            status = gateway_res.get("status", "PENDING")
            if status == "SUCCESS":
                completed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")
                if db.update_payout_status(
                    conversation_id=tracking_id,
                    status="SUCCESS",
                    transaction_id=tracking_id,
                    error_message="",
                    completed_at=completed_ts
                ):
                    db.adjust_balance(user_id, -payout_amount)
                    db.log_event(user_id, "INFO", f"[Scheduler Poll] Payout of KES {payout_amount:.2f} for {payout_date} confirmed SUCCESS. Tracking: {tracking_id}.")
            elif status == "FAILED":
                failed_ts = eat_now.strftime("%Y-%m-%d %H:%M:%S")
                if db.update_payout_status(
                    conversation_id=tracking_id,
                    status="FAILED",
                    transaction_id="",
                    error_message="Gateway confirmed FAILED",
                    failed_at=failed_ts
                ):
                    db.log_event(user_id, "ERROR", f"[Scheduler Poll] Payout for {payout_date} confirmed FAILED by gateway. Tracking: {tracking_id}.")
        except Exception as e:
            logger.warning(f"Payout poll error for tracking_id {tracking_id}: {e}")


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
                
                # Poll and resolve any stuck PENDING deposits and payouts
                loop.run_until_complete(poll_pending_deposits(db))
                loop.run_until_complete(poll_pending_payouts(db))

                # Fetch all registered users and process payouts individually
                users = db.get_all_users()
                for user in users:
                    user_id = user["id"]
                    settings = db.get_settings(user_id)
                    if settings:
                        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).replace(tzinfo=None)
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
