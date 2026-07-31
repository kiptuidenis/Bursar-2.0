import pytest
import re
import os

def test_xss_sanitization_in_app_js_sinks():
    """
    Verifies that all server-controlled dynamic variables rendered into innerHTML in app.js
    are wrapped with escapeHTML() to prevent XSS vulnerability SEC-004.
    """
    app_js_path = os.path.join(os.path.dirname(__file__), "..", "src", "app", "static", "js", "app.js")
    assert os.path.exists(app_js_path), "app.js file must exist"
    
    with open(app_js_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 1. Verify payout fields are escaped in payout table rendering
    assert "escapeHTML(payout.payout_date" in content or "escapeHTML(String(payout.payout_date" in content, \
        "payout.payout_date MUST be escaped with escapeHTML() in app.js"
        
    assert "escapeHTML(payout.phone_number" in content or "escapeHTML(String(payout.phone_number" in content, \
        "payout.phone_number MUST be escaped with escapeHTML() in app.js"
        
    assert "escapeHTML(payout.error_message" in content or "escapeHTML(String(payout.error_message" in content, \
        "payout.error_message MUST be escaped with escapeHTML() in app.js tooltips"
        
    # 2. Verify active session fields are escaped in session table rendering
    assert "escapeHTML(s.device" in content or "escapeHTML(String(s.device" in content, \
        "s.device MUST be escaped with escapeHTML() in active sessions table"
        
    assert "escapeHTML(s.ip_address" in content or "escapeHTML(String(s.ip_address" in content, \
        "s.ip_address MUST be escaped with escapeHTML() in active sessions table"
        
    assert "escapeHTML(s.created_at" in content or "escapeHTML(String(s.created_at" in content, \
        "s.created_at MUST be escaped with escapeHTML() in active sessions table"
        
    # 3. Verify budget lock notice dates are escaped
    assert "escapeHTML(currentSettings.start_date" in content or "escapeHTML(String(currentSettings.start_date" in content, \
        "currentSettings.start_date MUST be escaped with escapeHTML() in lock notice"
        
    assert "escapeHTML(currentSettings.end_date" in content or "escapeHTML(String(currentSettings.end_date" in content, \
        "currentSettings.end_date MUST be escaped with escapeHTML() in lock notice"
