import pytest
import os
import re

CSS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "src", "app", "static", "css", "style.css")

def test_css_zindex_stacking_hierarchy():
    """Verify that modal-overlay and stepup-payout-modal have higher z-index stacking than drawer-overlay."""
    assert os.path.exists(CSS_PATH), f"CSS file not found at {CSS_PATH}"
    
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        css_content = f.read()

    # Match .drawer-overlay z-index
    drawer_match = re.search(r'\.drawer-overlay\s*\{[^}]*z-index:\s*(\d+)', css_content)
    assert drawer_match, "Could not find z-index for .drawer-overlay"
    drawer_zindex = int(drawer_match.group(1))

    # Match .modal-overlay z-index
    modal_match = re.search(r'\.modal-overlay\s*\{[^}]*z-index:\s*(\d+)', css_content)
    assert modal_match, "Could not find z-index for .modal-overlay"
    modal_zindex = int(modal_match.group(1))

    # Match #stepup-payout-modal z-index
    stepup_match = re.search(r'#stepup-payout-modal\s*\{[^}]*z-index:\s*(\d+)', css_content)
    assert stepup_match, "Could not find z-index for #stepup-payout-modal"
    stepup_zindex = int(stepup_match.group(1))

    # Assert stacking order: stepup_zindex >= modal_zindex > drawer_zindex
    assert modal_zindex > drawer_zindex, f"Modal z-index ({modal_zindex}) must be greater than Drawer z-index ({drawer_zindex})"
    assert stepup_zindex >= modal_zindex, f"Stepup modal z-index ({stepup_zindex}) must be >= Modal z-index ({modal_zindex})"
    assert stepup_zindex > drawer_zindex, f"Stepup modal z-index ({stepup_zindex}) must be greater than Drawer z-index ({drawer_zindex})"
