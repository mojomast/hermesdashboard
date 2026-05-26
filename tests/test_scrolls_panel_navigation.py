from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.html"
APP = Path(__file__).resolve().parents[1] / "app.py"


def test_vesuvius_autoresearch_tab_is_registered_with_hash_router_and_breadcrumbs():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'data-panel="scrolls"' in html
    assert 'id="scrolls-panel"' in html
    assert "case 'scrolls': loadScrollsResearch(); break;" in html
    assert "'scrolls'" in html.split("const validPanels =", 1)[1].split(";", 1)[0]
    assert "scrolls:'Vesuvius AutoResearch'" in html or "'scrolls':'Vesuvius AutoResearch'" in html


def test_vesuvius_autoresearch_features_are_rendered_in_scrolls_panel():
    html = TEMPLATE.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    assert "Vesuvius AutoResearch Feature Inventory" in html
    assert "autoresearch_inventory" in html
    assert "renderScrollsFeatureInventory" in html
    assert "Seed-repeat LOO dry-run" in app
    assert "Verify prepared segments" in app
    assert "Build fold map dry-run" in app
    assert "Full-tile self-test" in app
    assert "Residual 2.5D smoke command" in app
    assert "Robust TTA config note" in app
    assert "Data expansion polite command" in app
    assert ".venv/bin/python" in app
    assert "Ignore archived/synthetic artifacts" in app
