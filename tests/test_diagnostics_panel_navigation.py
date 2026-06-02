from tests.dashboard_sources import dashboard_source


def test_diagnostics_tab_is_registered_with_hash_router_and_breadcrumbs():
    html = dashboard_source()

    assert 'data-panel="diagnostics"' in html
    assert "id=\"diagnostics-panel\"" in html
    assert "'diagnostics'" in html.split("const validPanels =", 1)[1].split(";", 1)[0]
    assert "diagnostics:'Diagnostics'" in html or "'diagnostics':'Diagnostics'" in html
