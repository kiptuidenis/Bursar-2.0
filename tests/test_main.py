import pytest
import os
import json
from fastapi.testclient import TestClient
from app.db.manager import DatabaseManager
from app.main import app, get_db

DB_FILE = "test_api_multitenant.db"
test_db_manager = None

def get_test_db():
    global test_db_manager
    if test_db_manager is None:
        test_db_manager = DatabaseManager(DB_FILE)
        test_db_manager.initialize()
    return test_db_manager

app.dependency_overrides[get_db] = get_test_db

@pytest.fixture(autouse=True)
def clean_db():
    db = get_test_db()
    conn = db.connection
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM settings")
    cursor.execute("DELETE FROM payouts")
    cursor.execute("DELETE FROM logs")
    cursor.execute("DELETE FROM budget_items")
    cursor.execute("DELETE FROM sessions")
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    yield

client = TestClient(app)

def test_unauthenticated_requests():
    # Calling settings, deposits, payouts, etc. without auth must return 401
    r1 = client.get("/api/settings")
    assert r1.status_code == 401
    assert "required" in r1.json()["detail"].lower()
    
    r2 = client.post("/api/deposit/initiate", json={"amount": 100})
    assert r2.status_code == 401
    
    r3 = client.get("/api/payouts")
    assert r3.status_code == 401

def test_signup_and_login_flow():
    # 1. Sign up new user
    signup_payload = {
        "phone_number": "254712345678",
        "password": "mypassword123"
    }
    res_signup = client.post("/api/auth/signup", json=signup_payload)
    assert res_signup.status_code == 200
    assert res_signup.json()["status"] == "success"
    
    # Sign up duplicate must fail
    res_dup = client.post("/api/auth/signup", json=signup_payload)
    assert res_dup.status_code == 400
    
    # 2. Login
    login_payload = {
        "phone_number": "254712345678",
        "password": "mypassword123"
    }
    
    # We use a fresh client to isolate cookie state
    c = TestClient(app)
    res_login = c.post("/api/auth/login", json=login_payload)
    assert res_login.status_code == 200
    assert "session_token" in res_login.cookies
    
    # 3. Verify /me endpoint
    res_me = c.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["phone_number"] == "254712345678"
    
    # 4. Access protected settings (should succeed now)
    res_settings = c.get("/api/settings")
    assert res_settings.status_code == 200
    assert res_settings.json()["balance"] == 0.0
    
    # 5. Logout
    res_logout = c.post("/api/auth/logout")
    assert res_logout.status_code == 200
    
    # Post logout, settings access should fail again
    res_settings_post = c.get("/api/settings")
    assert res_settings_post.status_code == 401

def test_user_data_isolation_via_api():
    # Create User A and User B
    client_a = TestClient(app)
    client_a.post("/api/auth/signup", json={"phone_number": "254711111111", "password": "pass"})
    client_a.post("/api/auth/login", json={"phone_number": "254711111111", "password": "pass"})
    
    client_b = TestClient(app)
    client_b.post("/api/auth/signup", json={"phone_number": "254722222222", "password": "pass"})
    client_b.post("/api/auth/login", json={"phone_number": "254722222222", "password": "pass"})
    
    # User A initiates deposit
    res_dep_a = client_a.post("/api/deposit/initiate", json={"amount": 1000.0})
    assert res_dep_a.status_code == 200
    checkout_id_a = res_dep_a.json()["checkout_request_id"]
    
    # User A simulates successful callback
    res_cb_a = client_a.post("/api/deposit/simulate-callback", json={"checkout_request_id": checkout_id_a, "status": "SUCCESS"})
    assert res_cb_a.status_code == 200
    
    # User B initiates deposit
    res_dep_b = client_b.post("/api/deposit/initiate", json={"amount": 500.0})
    assert res_dep_b.status_code == 200
    checkout_id_b = res_dep_b.json()["checkout_request_id"]
    
    # User B simulates successful callback
    res_cb_b = client_b.post("/api/deposit/simulate-callback", json={"checkout_request_id": checkout_id_b, "status": "SUCCESS"})
    assert res_cb_b.status_code == 200
    
    # Verify User A still has 1000, and User B has 500
    assert client_a.get("/api/settings").json()["balance"] == 1000.0
    assert client_b.get("/api/settings").json()["balance"] == 500.0

def test_settings_masked_updates_multi_tenant():
    c = TestClient(app)
    res_signup = c.post("/api/auth/signup", json={"phone_number": "254712345678", "password": "pass"})
    user_id = res_signup.json()["user_id"]
    c.post("/api/auth/login", json={"phone_number": "254712345678", "password": "pass"})
    
    payload = {
        "balance": 200.0,
        "daily_budget": 50.0,
        "mpesa_consumer_secret": "secret_key"
    }
    c.post("/api/settings", json=payload)
    
    # Check mask
    res1 = c.get("/api/settings").json()
    assert res1["mpesa_consumer_secret"] == "********"
    
    # Update balance with mask submitted (should preserve secret)
    c.post("/api/settings", json={"balance": 500.0, "mpesa_consumer_secret": "********"})
    
    db = get_test_db()
    settings = db.get_settings(user_id=user_id)
    assert settings["balance"] == 500.0
    assert settings["mpesa_consumer_secret"] == "secret_key"

def test_b2c_callbacks_success_and_failure():
    # 1. Signup user
    c = TestClient(app)
    res_signup = c.post("/api/auth/signup", json={"phone_number": "254712345678", "password": "pass"})
    user_id = res_signup.json()["user_id"]
    c.post("/api/auth/login", json={"phone_number": "254712345678", "password": "pass"})
    
    # 2. Add pending payout in database manually for User
    db = get_test_db()
    db.create_payout(
        user_id=user_id,
        payout_date="2026-06-18",
        amount=300.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id="conv_abc"
    )
    db.update_settings(user_id=user_id, balance=700.0) # Pre-deducted
    
    # 3. Trigger callback for success (anonymous webhook)
    success_payload = {
        "Result": {
            "ResultType": 0,
            "ResultCode": 0,
            "ResultDesc": "Success",
            "ConversationID": "conv_abc",
            "TransactionID": "MPESA123",
            "ResultParameters": None
        }
    }
    # Callback route does not require authentication
    res_cb = client.post("/api/callbacks/b2c-result", json=success_payload)
    assert res_cb.status_code == 200
    assert res_cb.json()["status"] == "acknowledged"
    
    # Verify DB state
    payout = db.get_payouts(user_id=user_id)[0]
    assert payout["status"] == "SUCCESS"
    assert payout["transaction_id"] == "MPESA123"
    assert db.get_settings(user_id=user_id)["balance"] == 700.0
    
    # 4. Add failed payout for User
    db.create_payout(
        user_id=user_id,
        payout_date="2026-06-19",
        amount=250.0,
        phone_number="254712345678",
        status="PENDING",
        conversation_id="conv_fail"
    )
    db.update_settings(user_id=user_id, balance=450.0) # Pre-deducted
    
    # Trigger callback for failure (anonymous webhook)
    fail_payload = {
        "Result": {
            "ResultType": 0,
            "ResultCode": 1032, # Cancelled
            "ResultDesc": "Request cancelled.",
            "ConversationID": "conv_fail",
            "TransactionID": "",
            "ResultParameters": None
        }
    }
    res_cb_fail = client.post("/api/callbacks/b2c-result", json=fail_payload)
    assert res_cb_fail.status_code == 200
    
    # Verify DB state (should be FAILED and balance refunded)
    payout_fail = db.get_payouts(user_id=user_id)[0]
    assert payout_fail["status"] == "FAILED"
    assert db.get_settings(user_id=user_id)["balance"] == 700.0  # 450 + 250 refund

def test_budget_items_api_flow():
    # Register and login a user to get session cookie
    signup_res = client.post("/api/auth/signup", json={"phone_number": "0722334455", "password": "passwordpin"})
    assert signup_res.status_code == 200
    login_res = client.post("/api/auth/login", json={"phone_number": "0722334455", "password": "passwordpin"})
    assert login_res.status_code == 200
    
    # 1. Fetch budget items (should be empty initially)
    fetch_res = client.get("/api/budget/items")
    assert fetch_res.status_code == 200
    assert fetch_res.json() == []
    
    # 2. Add budget item
    add_payload = {"category": "Food", "amount": 350.0}
    add_res = client.post("/api/budget/items", json=add_payload)
    assert add_res.status_code == 200
    assert add_res.json()["status"] == "success"
    
    # Verify settings daily_budget updated
    settings_res = client.get("/api/settings")
    assert settings_res.json()["daily_budget"] == 350.0
    
    # 3. Add second budget item
    add_res2 = client.post("/api/budget/items", json={"category": "Fare", "amount": 150.0})
    assert add_res2.status_code == 200
    
    # Verify total daily budget
    settings_res2 = client.get("/api/settings")
    assert settings_res2.json()["daily_budget"] == 500.0
    
    # Get items list
    items = client.get("/api/budget/items").json()
    assert len(items) == 2
    
    # 4. Delete item
    fare_item = next(item for item in items if item["category"] == "Fare")
    del_res = client.delete(f"/api/budget/items/{fare_item['id']}")
    assert del_res.status_code == 200
    
    # Verify total daily budget updated
    settings_res3 = client.get("/api/settings")
    assert settings_res3.json()["daily_budget"] == 350.0

def test_budget_items_api_unauthorized():
    # Instantiate a clean client to ensure no session cookies exist
    local_client = TestClient(app)
    
    # Try fetching without auth
    res = local_client.get("/api/budget/items")
    assert res.status_code == 401
    
    # Try adding without auth
    res_add = local_client.post("/api/budget/items", json={"category": "Test", "amount": 100.0})
    assert res_add.status_code == 401

def test_locking_api_constraints():
    c = TestClient(app)
    # 1. Signup & login
    c.post("/api/auth/signup", json={"phone_number": "254700000001", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000001", "password": "pinpassword"})
    
    # Verify settings are initially unlocked
    settings_res = c.get("/api/settings").json()
    assert settings_res["is_budget_locked"] is False
    assert settings_res["is_deposit_locked"] is False
    
    # Add a budget item
    add_item_res = c.post("/api/budget/items", json={"category": "Transport", "amount": 200.0})
    assert add_item_res.status_code == 200
    
    # Now deposit funds (this should auto-lock both because budget items exist)
    dep_res = c.post("/api/deposit/initiate", json={"amount": 1000.0})
    assert dep_res.status_code == 200
    checkout_id = dep_res.json()["checkout_request_id"]
    
    cb_res = c.post("/api/deposit/simulate-callback", json={"checkout_request_id": checkout_id, "status": "SUCCESS"})
    assert cb_res.status_code == 200
    
    settings_res2 = c.get("/api/settings").json()
    assert settings_res2["is_budget_locked"] is True
    assert settings_res2["is_deposit_locked"] is True
    
    # 2. Try adding another budget item (should fail with HTTP 400)
    fail_add = c.post("/api/budget/items", json={"category": "Food", "amount": 300.0})
    assert fail_add.status_code == 400
    assert "locked" in fail_add.json()["detail"].lower()
    
    # Try deleting the existing budget item (should fail with HTTP 400)
    items = c.get("/api/budget/items").json()
    item_id = items[0]["id"]
    fail_del = c.delete(f"/api/budget/items/{item_id}")
    assert fail_del.status_code == 400
    
    # 3. Try changing daily budget directly in settings (should fail with HTTP 400)
    fail_settings = c.post("/api/settings", json={"daily_budget": 500.0})
    assert fail_settings.status_code == 400
    
    # 4. Try manual budget lock endpoint
    # Create another client, signup and login
    c2 = TestClient(app)
    c2.post("/api/auth/signup", json={"phone_number": "254700000002", "password": "pinpassword"})
    c2.post("/api/auth/login", json={"phone_number": "254700000002", "password": "pinpassword"})
    
    # Try locking empty budget (should fail)
    fail_lock = c2.post("/api/budget/lock")
    assert fail_lock.status_code == 400
    
    # Add item and lock manually
    c2.post("/api/budget/items", json={"category": "Savings", "amount": 500.0})
    lock_res = c2.post("/api/budget/lock")
    assert lock_res.status_code == 200
    assert lock_res.json()["budget_locked_until"] != ""
    
    # Budget is locked now
    assert c2.get("/api/settings").json()["is_budget_locked"] is True

def test_settings_disbursement_dates():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000003", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000003", "password": "pinpassword"})
    
    # 1. Invalid date formats
    res1 = c.post("/api/settings", json={"start_date": "20-06-2026"})
    assert res1.status_code == 400
    
    res2 = c.post("/api/settings", json={"end_date": "2026/06/25"})
    assert res2.status_code == 400
    
    # 2. End date earlier than start date
    res3 = c.post("/api/settings", json={"start_date": "2026-06-25", "end_date": "2026-06-20"})
    assert res3.status_code == 400
    
    # 3. Successful update
    res4 = c.post("/api/settings", json={"start_date": "2026-06-20", "end_date": "2026-06-25"})
    assert res4.status_code == 200
    settings = c.get("/api/settings").json()
    assert settings["start_date"] == "2026-06-20"
    assert settings["end_date"] == "2026-06-25"


def test_lock_disbursement_dates():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000004", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000004", "password": "pinpassword"})
    
    # Add a budget item to make locking allowed
    c.post("/api/budget/items", json={"category": "Groceries", "amount": 400.0})
    
    # 1. Test invalid start date format
    res1 = c.post("/api/budget/lock", json={"start_date": "20-06-2026"})
    assert res1.status_code == 400
    
    # 2. Test invalid end date format
    res2 = c.post("/api/budget/lock", json={"end_date": "2026/06/25"})
    assert res2.status_code == 400
    
    # 3. Test end date earlier than start date
    res3 = c.post("/api/budget/lock", json={"start_date": "2026-06-25", "end_date": "2026-06-20"})
    assert res3.status_code == 400
    
    # 4. Successful lock with dates
    res4 = c.post("/api/budget/lock", json={"start_date": "2026-06-20", "end_date": "2026-06-25"})
    assert res4.status_code == 200
    assert res4.json()["start_date"] == "2026-06-20"
    assert res4.json()["end_date"] == "2026-06-25"
    
    # Verify budget locked and dates stored in settings
    settings = c.get("/api/settings").json()
    assert settings["is_budget_locked"] is True
    assert settings["start_date"] == "2026-06-20"
    assert settings["end_date"] == "2026-06-25"


def test_stk_push_and_callbacks():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000005", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000005", "password": "pinpassword"})
    
    # 1. Initiate STK Push deposit
    res_init = c.post("/api/deposit/initiate", json={"amount": 1500.0})
    assert res_init.status_code == 200
    checkout_id = res_init.json()["checkout_request_id"]
    
    # 2. Check pending status
    res_status = c.get(f"/api/deposit/status/{checkout_id}")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "PENDING"
    
    # 3. Simulate callback from Safaricom webhook (success)
    success_callback = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "mock-merchant-id",
                "CheckoutRequestID": checkout_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {
                            "Name": "Amount",
                            "Value": 1500.0
                        },
                        {
                            "Name": "MpesaReceiptNumber",
                            "Value": "NLJ7RT6KKH"
                        }
                    ]
                }
            }
        }
    }
    res_webhook = client.post("/api/callbacks/stk-callback", json=success_callback)
    assert res_webhook.status_code == 200
    assert res_webhook.json()["status"] == "acknowledged"
    
    # Check updated status (should be SUCCESS)
    res_status_sec = c.get(f"/api/deposit/status/{checkout_id}")
    assert res_status_sec.json()["status"] == "SUCCESS"
    
    # Check balance credited and deposit locked
    settings = c.get("/api/settings").json()
    assert settings["balance"] == 1500.0
    assert settings["is_deposit_locked"] is True
    
    # 4. Try initiating another deposit and simulating a failure callback
    res_init2 = c.post("/api/deposit/initiate", json={"amount": 2000.0})
    assert res_init2.status_code == 200
    checkout_id2 = res_init2.json()["checkout_request_id"]
    
    failed_callback = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "mock-merchant-id-2",
                "CheckoutRequestID": checkout_id2,
                "ResultCode": 1032,
                "ResultDesc": "Request cancelled by user."
            }
        }
    }
    res_webhook2 = client.post("/api/callbacks/stk-callback", json=failed_callback)
    assert res_webhook2.status_code == 200
    
    # Check status (should be FAILED)
    res_status_failed = c.get(f"/api/deposit/status/{checkout_id2}")
    assert res_status_failed.json()["status"] == "FAILED"
    
    # Balance should still be 1500.0 (unchanged)
    settings = c.get("/api/settings").json()
    assert settings["balance"] == 1500.0


def test_settings_payout_time_validation():
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000006", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000006", "password": "pinpassword"})
    
    # 1. Successful update with a future time (e.g. 15 minutes in the future)
    import datetime
    now = datetime.datetime.now()
    future_time = now + datetime.timedelta(minutes=15)
    
    # Handle overflow to next day safely by capping to 23:59 if it rolls over
    if future_time.date() > now.date():
        future_time_str = "23:59"
    else:
        future_time_str = future_time.strftime("%H:%M")
        
    res = c.post("/api/settings", json={"payout_time": future_time_str})
    assert res.status_code == 200
    
    # 2. Failed update with a past time (if not at 00:00)
    if now.hour > 0 or now.minute > 0:
        if now.minute > 0:
            past_time_str = f"{now.hour:02d}:00"
        else:
            past_time_str = f"{(now.hour - 1):02d}:59"
            
        res_past = c.post("/api/settings", json={"payout_time": past_time_str})
        assert res_past.status_code == 400
        assert "past" in res_past.json()["detail"].lower()


def test_intasend_integration_flow(monkeypatch):
    # Force PAYMENT_PROVIDER and INTASEND_MODE to use intasend simulation
    from app.services import payment_gateway
    monkeypatch.setattr(payment_gateway, "PAYMENT_PROVIDER", "intasend")
    monkeypatch.setattr(payment_gateway, "INTASEND_MODE", "simulation")

    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000007", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000007", "password": "pinpassword"})

    # 1. Initiate STK Push deposit using IntaSend
    res_init = c.post("/api/deposit/initiate", json={"amount": 3500.0})
    assert res_init.status_code == 200
    invoice_id = res_init.json()["checkout_request_id"]
    assert invoice_id.startswith("sim_invoice_")

    # 2. Check pending status in database
    db = get_test_db()
    deposit_db = db.get_deposit(invoice_id)
    assert deposit_db["status"] == "PENDING"
    assert deposit_db["amount"] == 3500.0

    # 3. Poll status dynamically.
    # The GET /api/deposit/status endpoint will query check_stk_status, which in simulation returns SUCCESS.
    # It should automatically mark it SUCCESS and credit the balance.
    res_status = c.get(f"/api/deposit/status/{invoice_id}")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "SUCCESS"

    # Confirm balance and locking
    settings = c.get("/api/settings").json()
    assert settings["balance"] == 3500.0
    assert settings["is_deposit_locked"] is True

    # 4. Initiate another deposit to test the webhook callback
    res_init2 = c.post("/api/deposit/initiate", json={"amount": 4000.0})
    assert res_init2.status_code == 200
    invoice_id2 = res_init2.json()["checkout_request_id"]

    # Post webhook callback from IntaSend
    webhook_payload = {
        "invoice_id": invoice_id2,
        "state": "COMPLETE",
        "provider": "M-PESA",
        "charges": "0.00",
        "net_amount": "4000.00",
        "currency": "KES",
        "value": "4000.00",
        "api_ref": "TEST_REF",
        "challenge": "testnet"
    }
    res_webhook = c.post("/api/callbacks/intasend-webhook", json=webhook_payload)
    assert res_webhook.status_code == 200
    assert res_webhook.json()["status"] == "acknowledged"

    # Check updated balance (3500 + 4000 = 7500)
    settings = c.get("/api/settings").json()
    assert settings["balance"] == 7500.0


def test_dashboard_endpoint_success():
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_dashboard_endpoint_missing(monkeypatch):
    import os
    original_exists = os.path.exists
    def mock_exists(path):
        if "dashboard.html" in path:
            return False
        return original_exists(path)
    monkeypatch.setattr(os.path, "exists", mock_exists)
    
    res = client.get("/dashboard")
    assert res.status_code == 404


def test_root_endpoint_success():
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_manual_payout_trigger_endpoint():
    # 1. Setup client user, signup & login
    c = TestClient(app)
    c.post("/api/auth/signup", json={"phone_number": "254700000008", "password": "pinpassword"})
    c.post("/api/auth/login", json={"phone_number": "254700000008", "password": "pinpassword"})
    
    # 2. Trigger payout (returns JSON triggered status)
    res = c.post("/api/payout/trigger")
    assert res.status_code == 200
    assert "triggered" in res.json()







