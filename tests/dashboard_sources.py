from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "templates"
TEMPLATE = TEMPLATE_DIR / "index.html"
DASHBOARD_CSS = ROOT / "static" / "css" / "dashboard.css"
DASHBOARD_JS = ROOT / "static" / "js" / "dashboard.js"


def raw_dashboard_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def dashboard_template() -> str:
    """Return rendered dashboard HTML, including Jinja partials."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
    )
    return env.get_template("index.html").render()


def dashboard_assets() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (DASHBOARD_CSS, DASHBOARD_JS)
    )


def dashboard_source() -> str:
    """Return rendered template plus extracted assets for source contract tests."""
    return dashboard_template() + "\n" + dashboard_assets()
