import re
from pathlib import Path

def test_dashboard_html_contains_footer_support_email():
    """Verify that dashboard.html footer has support@bursar.co.ke mailto link."""
    dashboard_path = Path("src/app/static/dashboard.html")
    assert dashboard_path.exists(), "dashboard.html does not exist"
    content = dashboard_path.read_text(encoding="utf-8")

    # Assert support link presence
    assert 'href="mailto:support@bursar.co.ke"' in content
    assert "support@bursar.co.ke" in content
    assert 'id="footer-support-link"' in content

    # Assert WhatsApp support contact presence in dashboard
    assert 'https://wa.me/254786918393' in content
    assert '+254786918393' in content
    assert 'id="footer-whatsapp-link"' in content


def test_landing_html_contains_footer_support_email_and_whatsapp():
    """Verify that index.html footer has support@bursar.co.ke and WhatsApp contact."""
    landing_path = Path("src/app/static/index.html")
    assert landing_path.exists(), "index.html does not exist"
    content = landing_path.read_text(encoding="utf-8")

    # Assert email and WhatsApp support contact in landing footer
    assert 'href="mailto:support@bursar.co.ke"' in content
    assert "support@bursar.co.ke" in content
    assert 'https://wa.me/254786918393' in content
    assert '+254786918393' in content


def test_style_css_contains_stationary_footer_and_whatsapp_rules():
    """Verify that style.css enforces stationary footer and WhatsApp link styling."""
    css_path = Path("src/app/static/css/style.css")
    assert css_path.exists(), "style.css does not exist"
    content = css_path.read_text(encoding="utf-8")

    # App container must be full height flex column
    assert ".app-container" in content
    assert "min-height: 100%" in content

    # Main content must contain overscroll-behavior
    assert "overscroll-behavior-y: contain" in content

    # Footer support link styling
    assert ".footer-support-link" in content
    assert ".footer-whatsapp-link" in content
    assert "#25D366" in content
