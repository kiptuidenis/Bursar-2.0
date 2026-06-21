import pytest
from app.services.intasend import IntasendClient

@pytest.mark.asyncio
async def test_intasend_client_initialization():
    client = IntasendClient(
        secret_key="ISSecretKey_test_mock",
        publishable_key="ISPubKey_test_mock",
        mode="simulation"
    )
    assert client.secret_key == "ISSecretKey_test_mock"
    assert client.publishable_key == "ISPubKey_test_mock"
    assert client.mode == "simulation"
    assert client.base_url == "https://sandbox.intasend.com/api"

@pytest.mark.asyncio
async def test_intasend_client_live_url():
    client = IntasendClient(
        secret_key="ISSecretKey_live_mock",
        publishable_key="ISPubKey_live_mock",
        mode="live"
    )
    assert client.base_url == "https://payment.intasend.com/api"

@pytest.mark.asyncio
async def test_intasend_stk_push_simulation():
    client = IntasendClient(
        secret_key="mock",
        publishable_key="mock",
        mode="simulation"
    )
    res = await client.initiate_stk_push(
        phone_number="254712345678",
        amount=100.0,
        api_ref="TEST_REF"
    )
    assert "invoice" in res
    invoice = res["invoice"]
    assert invoice["state"] == "PENDING"
    assert invoice["net_amount"] == 100.0
    assert invoice["api_ref"] == "TEST_REF"
    assert invoice["id"].startswith("sim_invoice_")

@pytest.mark.asyncio
async def test_intasend_stk_status_simulation():
    client = IntasendClient(
        secret_key="mock",
        publishable_key="mock",
        mode="simulation"
    )
    res = await client.check_stk_status(invoice_id="sim_invoice_123")
    assert "invoice" in res
    invoice = res["invoice"]
    assert invoice["state"] == "COMPLETE"
    assert invoice["invoice_id"] == "sim_invoice_123"

@pytest.mark.asyncio
async def test_intasend_b2c_payout_simulation():
    client = IntasendClient(
        secret_key="mock",
        publishable_key="mock",
        mode="simulation"
    )
    res = await client.send_b2c_payout(
        phone_number="254712345678",
        amount=500.0,
        recipient_name="Test User",
        narrative="Monthly Payout"
    )
    assert "tracking_id" in res
    assert res["status"] == "Completed"
    assert res["tracking_id"].startswith("sim_tracking_")

@pytest.mark.asyncio
async def test_intasend_payout_status_simulation():
    client = IntasendClient(
        secret_key="mock",
        publishable_key="mock",
        mode="simulation"
    )
    res = await client.check_payout_status(tracking_id="sim_tracking_abc")
    assert res["tracking_id"] == "sim_tracking_abc"
    assert res["status"] == "Completed"
