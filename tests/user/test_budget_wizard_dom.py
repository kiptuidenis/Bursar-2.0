import os
import re
import pytest

def test_budget_wizard_dom_structure():
    """Verify that dashboard.html contains all necessary components for the 3-step sliding wizard."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "app", "static", "dashboard.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Wizard Track Container
    assert 'id="budget-wizard-container"' in html or 'class="budget-wizard-container"' in html
    assert 'id="budget-wizard-track"' in html

    # 2. Wizard Header & Progress Dots
    assert 'id="budget-wizard-step-title"' in html or 'id="budget-wizard-header"' in html
    assert 'id="budget-wizard-dots"' in html or 'class="wizard-step-dots"' in html

    # 3. Tiles 1, 2, and 3
    assert 'id="budget-wizard-tile-1"' in html
    assert 'id="budget-wizard-tile-2"' in html
    assert 'id="budget-wizard-tile-3"' in html

    # 4. Step Navigation Buttons
    assert 'id="budget-wizard-next-1"' in html
    assert 'id="budget-wizard-back-2"' in html
    assert 'id="budget-wizard-next-2"' in html
    assert 'id="budget-wizard-back-3"' in html
    assert 'id="lock-budget-btn"' in html

    # 5. Tile 1 Components (Categories & Total)
    assert 'id="add-category-form"' in html
    assert 'id="new-category-name"' in html
    assert 'id="new-category-amount"' in html
    assert 'id="designer-category-list"' in html
    assert 'id="designer-total-budget"' in html

    # 6. Tile 2 Components (Start & End Dates)
    assert 'id="lock-start-date"' in html
    assert 'id="lock-end-date"' in html

    # 7. Tile 3 Components (Target Payout Phone)
    assert 'id="budget-lock-payout-phone"' in html

def test_budget_wizard_css_track_and_tile_proportions():
    """Verify that style.css enforces 300% track width and 33.333333% tile flex bases to prevent horizontal bleed."""
    css_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "app", "static", "css", "style.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    assert ".budget-wizard-container" in css
    assert ".budget-wizard-track" in css
    assert "width: 300%" in css
    assert "33.333333%" in css

def test_budget_wizard_js_step_offset_formula():
    """Verify that app.js calculates offset based on 300% track proportions (100 / 3) to prevent slide overlap."""
    js_path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "app", "static", "js", "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert "goToBudgetWizardStep" in js
    assert "(100 / 3)" in js or "33.333333" in js
