import os
import re
import pytest
from html.parser import HTMLParser
from app.core.security_headers import SECURITY_HEADERS

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "src", "app", "static")
INDEX_PATH = os.path.join(STATIC_DIR, "index.html")
DASHBOARD_PATH = os.path.join(STATIC_DIR, "dashboard.html")
VENDOR_DIR = os.path.join(STATIC_DIR, "js", "vendor")

class ResourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "script":
            self.scripts.append(attr_dict)
        elif tag == "link":
            self.links.append(attr_dict)

def get_parsed_html(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    parser = ResourceParser()
    parser.feed(content)
    return content, parser

def test_self_hosted_vendor_files_exist():
    lucide_path = os.path.join(VENDOR_DIR, "lucide.min.js")
    chart_path = os.path.join(VENDOR_DIR, "chart.umd.min.js")
    assert os.path.isfile(lucide_path), f"Missing self-hosted vendor file: {lucide_path}"
    assert os.path.isfile(chart_path), f"Missing self-hosted vendor file: {chart_path}"
    assert os.path.getsize(lucide_path) > 1000, "lucide.min.js file is unexpectedly empty"
    assert os.path.getsize(chart_path) > 1000, "chart.umd.min.js file is unexpectedly empty"

def test_no_unpinned_latest_tags_in_html():
    for path in [INDEX_PATH, DASHBOARD_PATH]:
        content, _ = get_parsed_html(path)
        assert "@latest" not in content, f"Found unpinned '@latest' tag in {os.path.basename(path)}"

def test_external_resources_use_https_only():
    for path in [INDEX_PATH, DASHBOARD_PATH]:
        _, parser = get_parsed_html(path)
        
        # Check script tags
        for script in parser.scripts:
            src = script.get("src", "")
            if src.startswith("//"):
                pytest.fail(f"Protocol-relative URL found in {os.path.basename(path)}: {src}")
            if src.startswith("http://"):
                pytest.fail(f"Insecure HTTP script URL found in {os.path.basename(path)}: {src}")

        # Check link tags
        for link in parser.links:
            href = link.get("href", "")
            if href.startswith("//"):
                pytest.fail(f"Protocol-relative URL found in {os.path.basename(path)}: {href}")
            if href.startswith("http://"):
                pytest.fail(f"Insecure HTTP link URL found in {os.path.basename(path)}: {href}")

def test_external_scripts_and_styles_have_integrity_and_crossorigin():
    for path in [INDEX_PATH, DASHBOARD_PATH]:
        _, parser = get_parsed_html(path)

        # Audit external script tags
        for script in parser.scripts:
            src = script.get("src", "")
            if src.startswith("https://"):
                integrity = script.get("integrity", "")
                crossorigin = script.get("crossorigin", "")
                assert integrity.startswith("sha384-"), f"External script {src} in {os.path.basename(path)} missing valid sha384 integrity hash"
                assert crossorigin in ["anonymous", "use-credentials"], f"External script {src} in {os.path.basename(path)} missing crossorigin attribute"

        # Audit external link stylesheet tags
        for link in parser.links:
            href = link.get("href", "")
            rel = link.get("rel", "")
            if "stylesheet" in rel and href.startswith("https://") and "fonts.googleapis.com" not in href:
                integrity = link.get("integrity", "")
                crossorigin = link.get("crossorigin", "")
                assert integrity.startswith("sha384-"), f"External stylesheet {href} in {os.path.basename(path)} missing sha384 integrity hash"
                assert crossorigin in ["anonymous", "use-credentials"], f"External stylesheet {href} in {os.path.basename(path)} missing crossorigin attribute"

def test_security_headers_csp_minimal_origins():
    csp = SECURITY_HEADERS.get("Content-Security-Policy", "")
    assert "font-src" in csp, "CSP missing explicit font-src directive"
    assert "https://unpkg.com" not in csp, "CSP contains unneeded unpkg.com origin after self-hosting vendor scripts"
    assert "https://cdn.jsdelivr.net" not in csp, "CSP contains unneeded jsdelivr.net origin after self-hosting vendor scripts"
