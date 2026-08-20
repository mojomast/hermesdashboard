from pathlib import Path

import app as dashboard_app
from jinja2 import Environment, FileSystemLoader


def test_brand_gallery_route_and_options():
    routes = {getattr(route, "path", None): getattr(route, "endpoint", None) for route in dashboard_app.routes}
    assert routes["/brand-gallery"] is dashboard_app.brand_gallery

    templates = Path(__file__).parents[1] / "templates"
    html = Environment(loader=FileSystemLoader(templates)).get_template("brand_gallery.html").render()
    assert html.count('class="concept ') == 110
    assert html.count('class="studio-anchor"') == 10
    assert 'href="#studio-10"' in html
    assert "hermes_dashboard_brand_concept_v1" in html
    assert "concept.tabIndex = 0" in html
    assert "concept.setAttribute('aria-pressed'" in html
    assert "brand-embed-context" in html
    assert "Use default text" in html
    assert "prefers-reduced-motion: reduce" in html
    assert "Hermes Dashboard" in html


def test_dashboard_header_loads_selected_brand_with_fallback():
    root = Path(__file__).parents[1]
    nav = (root / "templates" / "dashboard" / "partials" / "nav.html").read_text(encoding="utf-8")
    script = (root / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")
    css = (root / "static" / "css" / "dashboard.css").read_text(encoding="utf-8")

    assert 'id="dashboard-logo-default"' in nav
    assert 'id="dashboard-logo-preview"' in nav
    assert 'href="/brand-gallery"' in nav
    assert "function applyDashboardBrandSelection()" in script
    assert "`/brand-gallery?embed=${selectedId}`" in script
    assert "frame.onload" in script
    assert ".dashboard-logo-preview" in css
