import pytest
import os
import re

JS_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "app", "static", "js", "app.js")
HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "app", "static", "dashboard.html")

def test_stepup_modal_dynamic_button_labels_in_js():
    """Verify that app.js sets 'Save' for settings and 'Lock Budget' for budget lock."""
    with open(JS_PATH, "r", encoding="utf-8") as f:
        js_content = f.read()

    # Verify context === "settings" sets Save button
    assert 'confirmBtn.innerHTML = \'<i data-lucide="check" style="width: 1rem; height: 1rem;"></i> Save\';' in js_content or \
           'Save' in js_content and 'context === "settings"' in js_content

    # Verify context !== "settings" sets Lock Budget button
    assert 'Lock Budget' in js_content

def test_stepup_modal_default_button_in_dashboard_html():
    """Verify dashboard.html default confirm button in stepup modal."""
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    assert 'id="confirm-stepup-payout-btn"' in html_content
    assert 'Save' in html_content
