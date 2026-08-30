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
