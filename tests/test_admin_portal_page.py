import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_admin_portal_html_served_at_admin_route():
    """Verify /admin serves admin.html with proper no-cache headers."""
    with TestClient(app) as client:
        res = client.get("/admin")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "Bursar Admin Portal" in res.text
        assert "no-store" in res.headers.get("cache-control", "")

def test_admin_static_assets_accessible():
    """Verify admin CSS and JS static files are served."""
    with TestClient(app) as client:
        res_css = client.get("/css/admin.css")
        assert res_css.status_code == 200
        assert "text/css" in res_css.headers["content-type"]

        res_js = client.get("/js/admin.js")
        assert res_js.status_code == 200
        assert "javascript" in res_js.headers["content-type"]

def test_admin_portal_user_360_and_notification_modals_present():
    """Verify that User 360 inspection drawer and Send Notification modals are mounted in HTML."""
    with TestClient(app) as client:
        res = client.get("/admin")
        assert res.status_code == 200
        html = res.text
        
        # Verify User Directory Table & Search Controls
        assert 'id="pane-users"' in html
        assert 'id="users-table"' in html
        assert 'id="users-search-input"' in html
        assert 'id="users-status-filter"' in html

        # Verify User 360 Modal
        assert 'id="modal-user-360"' in html
        assert 'id="u360-modal-title"' in html
        assert 'id="u360-modal-body"' in html

        # Verify Send Notification Modal & Form Elements
        assert 'id="modal-send-notification"' in html
        assert 'id="form-send-notification"' in html
        assert 'id="notif-user-id"' in html
        assert 'id="notif-user-display"' in html
        assert 'id="notif-title"' in html
        assert 'id="notif-type"' in html
        assert 'id="notif-message"' in html
        assert 'id="notif-reason"' in html
        assert 'id="btn-submit-send-notif"' in html

def test_admin_portal_finances_and_adjust_balance_modal_present():
    """Verify that Finances ledger pane, live total balance chip, and Balance Adjustment modal are mounted in HTML."""
    with TestClient(app) as client:
        res = client.get("/admin")
        assert res.status_code == 200
        html = res.text

        # Verify Finances Pane & Table
        assert 'id="pane-finances"' in html
        assert 'id="finances-total-balance"' in html
        assert 'id="wallets-table"' in html
        assert 'id="wallets-table-body"' in html
        assert 'id="wallets-search-input"' in html
        assert 'id="btn-open-balance-adjust"' in html
        assert 'id="wallets-pagination"' in html

        # Verify Adjust Balance Modal & Form Fields
        assert 'id="modal-adjust-balance"' in html
        assert 'id="form-adjust-balance"' in html
        assert 'id="adj-user-id"' in html
        assert 'id="adj-user-display"' in html
        assert 'id="adj-type"' in html
        assert 'id="adj-amount"' in html
        assert 'id="adj-reference"' in html
        assert 'id="adj-reason"' in html
        assert 'id="btn-submit-adjust"' in html


