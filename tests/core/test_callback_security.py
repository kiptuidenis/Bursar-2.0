import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_db
from app.core import config
from app.db.manager import DatabaseManager

TEST_DB_FILE = "test_callback_sec.db"

@pytest.fixture
def test_db():
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass

    manager = DatabaseManager(TEST_DB_FILE)
    manager.initialize()
    yield manager
    manager.close()

    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


def _db_override(manager):
    def override():
        yield manager
    return override


# ===========================================================================
# 1. Callback endpoints reject unauthorized requests in production mode
# ===========================================================================

def test_stk_callback_requires_valid_secret_token(test_db, monkeypatch):
    """STK callback must reject unauthenticated requests without valid secret token in production mode."""
    monkeypatch.setattr(config, "IS_DEV_MODE", False)
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    monkeypatch.setattr(config, "CALLBACK_SECRET_TOKEN", "prod_callback_secret_token_32chars_min")

    old_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        client = TestClient(app)
        payload = {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": "req_123",
                    "ResultCode": 0,
                    "ResultDesc": "Success"
                }
            }
        }

        # 1. Request with no token -> 401 Unauthorized
        res_no_token = client.post("/api/callbacks/stk-callback", json=payload)
        assert res_no_token.status_code == 401
        assert "Unauthorized" in res_no_token.json()["detail"]

        # 2. Request with invalid token -> 401 Unauthorized
        res_bad_token = client.post("/api/callbacks/stk-callback?token=wrong_token", json=payload)
        assert res_bad_token.status_code == 401

        # 3. Request with valid token in header -> Accepted
        res_valid = client.post(
            "/api/callbacks/stk-callback",
            json=payload,
            headers={"X-Callback-Secret": "prod_callback_secret_token_32chars_min"}
        )
        assert res_valid.status_code == 200

    finally:
        if old_override is not None:
            app.dependency_overrides[get_db] = old_override
        else:
            app.dependency_overrides.pop(get_db, None)


def test_b2c_callbacks_require_valid_secret_token(test_db, monkeypatch):
    """B2C result and timeout callbacks must reject unauthenticated requests without valid secret token."""
    monkeypatch.setattr(config, "IS_DEV_MODE", False)
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    monkeypatch.setattr(config, "CALLBACK_SECRET_TOKEN", "prod_callback_secret_token_32chars_min")

    old_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        client = TestClient(app)
        payload = {
            "Result": {
                "ConversationID": "conv_999",
                "ResultCode": 0,
                "ResultDesc": "Success"
            }
        }

        # B2C result without token -> 401
        res_b2c = client.post("/api/callbacks/b2c-result", json=payload)
        assert res_b2c.status_code == 401

        # B2C timeout without token -> 401
        res_timeout = client.post("/api/callbacks/b2c-timeout", json={"ConversationID": "conv_999"})
        assert res_timeout.status_code == 401

        # B2C result with valid query parameter token -> Accepted
        res_b2c_valid = client.post(
            "/api/callbacks/b2c-result?token=prod_callback_secret_token_32chars_min",
            json=payload
        )
        assert res_b2c_valid.status_code == 200

    finally:
        if old_override is not None:
            app.dependency_overrides[get_db] = old_override
        else:
            app.dependency_overrides.pop(get_db, None)


def test_intasend_webhook_challenge_verification(test_db, monkeypatch):
    """IntaSend webhook must reject requests with invalid challenge or secret token."""
    monkeypatch.setattr(config, "IS_DEV_MODE", False)
    monkeypatch.setattr(config, "IS_TEST_MODE", False)
    monkeypatch.setattr(config, "CALLBACK_SECRET_TOKEN", "prod_callback_secret_token_32chars_min")
    monkeypatch.setattr(config, "INTASEND_WEBHOOK_CHALLENGE", "intasend_secure_challenge_key")

    old_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        client = TestClient(app)
        payload = {"invoice_id": "inv_fake_001", "challenge": "invalid_challenge"}

        # Request with invalid challenge -> 401
        res = client.post("/api/callbacks/intasend-webhook", json=payload)
        assert res.status_code == 401

        # Request with valid challenge in body -> Accepted
        payload_valid = {"invoice_id": "inv_fake_001", "challenge": "intasend_secure_challenge_key"}
        res_valid = client.post("/api/callbacks/intasend-webhook", json=payload_valid)
        assert res_valid.status_code == 200

    finally:
        if old_override is not None:
            app.dependency_overrides[get_db] = old_override
        else:
            app.dependency_overrides.pop(get_db, None)


# ===========================================================================
# 2. Production Protection for Simulation Endpoints
# ===========================================================================

def test_simulate_callback_disabled_in_production(test_db, monkeypatch):
    """Simulated callback route must return 403 Forbidden in production mode for authenticated users."""
    monkeypatch.setattr(config, "IS_DEV_MODE", False)
    monkeypatch.setattr(config, "IS_TEST_MODE", False)

    from app.api.dependencies import get_current_user_id
    old_db_override = app.dependency_overrides.get(get_db)
    old_auth_override = app.dependency_overrides.get(get_current_user_id)

    app.dependency_overrides[get_db] = _db_override(test_db)
    app.dependency_overrides[get_current_user_id] = lambda: 1  # Mock logged in user 1

    try:
        client = TestClient(app)
        res = client.post(
            "/api/deposit/simulate-callback",
            json={"checkout_request_id": "sim_123", "status": "SUCCESS"}
        )
        assert res.status_code == 403
        assert "disabled in production" in res.json()["detail"].lower()

    finally:
        if old_db_override is not None:
            app.dependency_overrides[get_db] = old_db_override
        else:
            app.dependency_overrides.pop(get_db, None)

        if old_auth_override is not None:
            app.dependency_overrides[get_current_user_id] = old_auth_override
        else:
            app.dependency_overrides.pop(get_current_user_id, None)



# ===========================================================================
# 3. IP Whitelisting Validation
# ===========================================================================

def test_ip_whitelisting_rejects_unauthorized_origin_ip(test_db, monkeypatch):
    """Callback requests originating from IPs outside ALLOWED_CALLBACK_IPS must be rejected."""
    monkeypatch.setattr(config, "ALLOWED_CALLBACK_IPS", ["196.201.214.20", "196.201.214.21"])

    old_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db_override(test_db)

    try:
        client = TestClient(app)
        res = client.post(
            "/api/callbacks/stk-callback?token=ci_test_callback_secret_token_32chars_minimum",
            json={"Body": {"stkCallback": {"CheckoutRequestID": "123"}}}
        )
        assert res.status_code == 401
        assert "IP address is not permitted" in res.json()["detail"]

    finally:
        if old_override is not None:
            app.dependency_overrides[get_db] = old_override
        else:
            app.dependency_overrides.pop(get_db, None)
