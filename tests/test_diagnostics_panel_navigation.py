from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.html"


def test_diagnostics_tab_is_registered_with_hash_router_and_breadcrumbs():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'data-panel="diagnostics"' in html
    assert "id=\"diagnostics-panel\"" in html
    assert "'diagnostics'" in html.split("const validPanels =", 1)[1].split(";", 1)[0]
    assert "diagnostics:'Diagnostics'" in html or "'diagnostics':'Diagnostics'" in html
