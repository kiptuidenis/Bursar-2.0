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

def test_style_css_contains_stationary_footer_rules():
    """Verify that style.css enforces full height container and overscroll containment for stationary footer."""
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
