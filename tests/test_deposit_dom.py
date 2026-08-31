import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_dashboard_deposit_phone_dom_elements_present():
    """Verify that deposit phone input group, label, input, and hint are mounted in dashboard.html."""
    with TestClient(app) as client:
        res = client.get("/dashboard.html")
        assert res.status_code == 200
        html = res.text

        assert 'id="deposit-form"' in html
        assert 'id="deposit-phone-group"' in html
        assert 'id="deposit-phone"' in html
        assert 'id="deposit-phone-status-badge"' in html
        assert 'id="deposit-phone-hint"' in html
        assert 'id="deposit-amount"' in html
