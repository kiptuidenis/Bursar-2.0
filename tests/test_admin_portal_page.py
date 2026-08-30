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

def test_admin_portal_deposits_and_manual_settle_modal_present():
    """Verify that Deposits pane, status filter, table, volume stat, and Manual Settle modal are mounted in HTML."""
    with TestClient(app) as client:
        res = client.get("/admin")
        assert res.status_code == 200
        html = res.text

        # Verify Deposits Pane & Table
        assert 'id="pane-deposits"' in html
        assert 'id="deposits-total-volume"' in html
        assert 'id="deposits-table"' in html
        assert 'id="deposits-table-body"' in html
        assert 'id="deposits-search-input"' in html
        assert 'id="deposits-status-filter"' in html
        assert 'id="deposits-pagination"' in html

        # Verify Manual Settle Modal & Form Fields
        assert 'id="modal-manual-settle-deposit"' in html
        assert 'id="form-manual-settle-deposit"' in html
        assert 'id="settle-checkout-id"' in html
        assert 'id="settle-checkout-display"' in html
        assert 'id="settle-mpesa-receipt"' in html
        assert 'id="settle-reason"' in html
        assert 'id="btn-submit-settle-deposit"' in html

def test_admin_portal_payouts_and_retry_settle_modals_present():
    """Verify that Payouts pane, table, total disbursed stat, trigger batch button, and Retry/Settle modals are mounted in HTML."""
    with TestClient(app) as client:
        res = client.get("/admin")
        assert res.status_code == 200
        html = res.text

        # Verify Payouts Pane & Table
        assert 'id="pane-payouts"' in html
        assert 'id="payouts-total-disbursed"' in html
        assert 'id="payouts-table"' in html
        assert 'id="payouts-table-body"' in html
        assert 'id="payouts-search-input"' in html
        assert 'id="payouts-status-filter"' in html
        assert 'id="btn-open-trigger-batch"' in html
        assert 'id="payouts-pagination"' in html

        # Verify Retry Payout Modal
        assert 'id="modal-retry-payout"' in html
        assert 'id="form-retry-payout"' in html
        assert 'id="retry-payout-id"' in html
        assert 'id="retry-payout-display"' in html
        assert 'id="retry-payout-reason"' in html
        assert 'id="btn-submit-retry-payout"' in html

        # Verify Manual Settle Payout Modal
        assert 'id="modal-manual-settle-payout"' in html
        assert 'id="form-manual-settle-payout"' in html
        assert 'id="settle-payout-id"' in html
        assert 'id="settle-payout-display"' in html
        assert 'id="settle-payout-tx"' in html
        assert 'id="settle-payout-reason"' in html
        assert 'id="btn-submit-settle-payout"' in html

def test_admin_portal_audit_logs_and_payload_modal_present():
    """Verify that Audit Logs pane, table, action filter, CSV export button, and Payload Inspector modal are mounted in HTML."""
    with TestClient(app) as client:
        res = client.get("/admin")
        assert res.status_code == 200
        html = res.text

        # Verify Audit Logs Pane & Controls
        assert 'id="pane-audit"' in html
        assert 'id="audit-table"' in html
        assert 'id="audit-table-body"' in html
        assert 'id="audit-search-input"' in html
        assert 'id="audit-action-filter"' in html
        assert 'id="btn-export-audit-csv"' in html
        assert 'id="audit-pagination"' in html

        # Verify Payload Inspector Modal
        assert 'id="modal-audit-payload"' in html
        assert 'id="audit-before-state"' in html
        assert 'id="audit-after-state"' in html
        assert 'id="audit-payload-reason"' in html





