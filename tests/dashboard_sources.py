from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "index.html"
DASHBOARD_CSS = ROOT / "static" / "css" / "dashboard.css"
DASHBOARD_JS = ROOT / "static" / "js" / "dashboard.js"


def dashboard_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def dashboard_assets() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (DASHBOARD_CSS, DASHBOARD_JS)
    )


def dashboard_source() -> str:
    """Return template plus extracted assets for raw-source contract tests."""
    return dashboard_template() + "\n" + dashboard_assets()
