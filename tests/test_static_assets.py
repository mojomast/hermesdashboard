import app as dashboard_app
from tests.dashboard_sources import DASHBOARD_CSS, DASHBOARD_JS, dashboard_template


def test_dashboard_template_links_extracted_static_assets():
    html = dashboard_template()

    assert '<link rel="stylesheet" href="/static/css/dashboard.css">' in html
    assert '<script src="/static/js/dashboard.js" defer></script>' in html
    assert '<style>' not in html
    assert 'type="module"' not in html


def test_extracted_assets_exist_and_keep_expected_contracts():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert '* { margin: 0; padding: 0; box-sizing: border-box; }' in css
    assert 'function initTheme()' in js
    assert 'function toggleTheme()' in js
    assert 'export default' not in js
    assert 'export {' not in js


def test_static_route_is_registered_with_extracted_asset_directory():
    static_routes = [route for route in dashboard_app.routes if getattr(route, "path", None) == "/static"]
    assert len(static_routes) == 1

    static_app = getattr(static_routes[0], "app", None)
    directory = getattr(static_app, "directory", None)
    if directory is None:
        directory = getattr(static_app, "kwargs", {}).get("directory")

    assert str(directory).endswith("static")
