import os
import re
import pytest

def test_wallet_withdrawal_dom_structure():
    """Verify that dashboard.html contains all required elements for cash withdrawal and 2FA authorization."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "app", "static", "dashboard.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Debit Card Withdraw Button
    assert 'id="open-withdraw-btn"' in html
    assert 'Withdraw' in html

    # 2. Cash Withdrawal Initial Modal
    assert 'id="withdraw-modal"' in html
    assert 'id="withdraw-form"' in html
    assert 'id="withdraw-available-bal"' in html
    assert 'id="withdraw-dest-phone"' in html
    assert 'id="withdraw-amount-input"' in html
    assert 'btn-quick-withdraw' in html
    assert 'id="btn-withdraw-max"' in html
    assert 'id="proceed-withdraw-btn"' in html
    assert 'id="cancel-withdraw-btn"' in html
    assert 'id="close-withdraw-btn"' in html

    # 3. Cash Withdrawal 2FA Step-Up Modal
    assert 'id="withdraw-2fa-modal"' in html
    assert 'id="withdraw-2fa-form"' in html
    assert 'id="withdraw-confirm-amount"' in html
    assert 'id="withdraw-confirm-dest"' in html
    assert 'id="withdraw-auth-password"' in html
    assert 'id="withdraw-auth-otp"' in html
    assert 'id="resend-withdraw-otp-btn"' in html
    assert 'id="confirm-withdraw-submit-btn"' in html
    assert 'id="back-withdraw-2fa-btn"' in html
    assert 'id="close-withdraw-2fa-btn"' in html

def test_wallet_withdrawal_js_handlers_and_lifecycle():
    """Verify that app.js implements the complete button lifecycle, validation, and 2FA withdrawal flow."""
    js_path = os.path.join(os.path.dirname(__file__), "..", "src", "app", "static", "js", "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    # 1. Event setup invocation
    assert "setupWithdrawalHandlers();" in js
    assert "function setupWithdrawalHandlers()" in js

    # 2. Lifecycle: Hide when deposit locked, Show when unlocked and balance >= 10
    assert "!settings.is_deposit_locked" in js
    assert 'openWithdrawBtn.style.display = "inline-flex"' in js
    assert 'openWithdrawBtn.style.display = "none"' in js

    # 3. Pre-OTP Request
    assert '"/api/profile/request-stepup-otp"' in js
    assert 'purpose: "wallet_withdrawal"' in js

    # 4. 2FA Submission & Idempotency Key
    assert '"/api/wallet/withdraw"' in js
    assert '"Idempotency-Key":' in js
    assert "crypto.randomUUID" in js or "Math.random" in js
