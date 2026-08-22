import asyncio
import json

import app as dashboard_app
from dashboard_backend.services.files import FileService
from tests.dashboard_sources import DASHBOARD_CSS, DASHBOARD_JS, dashboard_template


class FakeRequest:
    def __init__(self, query_params=None):
        self.query_params = query_params or {}


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def test_capabilities_and_files_are_first_class_responsive_panels():
    html = dashboard_template()
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    css = DASHBOARD_CSS.read_text(encoding="utf-8")

    for panel, label in (("capabilities", "Capabilities"), ("files", "Files")):
        assert f'id="{panel}-panel"' in html
        assert html.count(f'data-panel="{panel}"') == 2
        assert f"navigateTo('{panel}')" in html
        assert f"{{ id: '{panel}', label: '{label}' }}" in js
        assert f"case '{panel}':" in js
    assert "function loadCapabilities(" in js
    assert "function loadFileManager(" in js
    assert "function renderUniversalFileViewer(" in js
    assert "'/api/capabilities'" in js
    assert "'/api/files/projects'" in js
    assert "'/api/files/list'" in js
    assert "'/api/files/meta'" in js
    assert "'/api/files/preview'" in js
    assert "'/api/files/raw'" in js
    assert "'/api/files/download'" in js
    assert ".capability-layout" in css
    assert ".file-manager-layout" in css
    assert "@media (max-width: 640px)" in css


def test_file_routes_are_registered_and_project_scoped(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "hello.txt").write_text("hello world", encoding="utf-8")
    service = FileService({"Project": root})
    monkeypatch.setattr(dashboard_app, "_dashboard_file_service", lambda: service)

    projects = response_json(asyncio.run(dashboard_app.get_file_projects(FakeRequest())))
    listing = response_json(asyncio.run(dashboard_app.list_project_files(FakeRequest({"project": "project", "path": ""}))))
    metadata = response_json(asyncio.run(dashboard_app.get_file_metadata(FakeRequest({"project": "project", "path": "hello.txt"}))))
    preview = response_json(asyncio.run(dashboard_app.get_file_preview(FakeRequest({"project": "project", "path": "hello.txt"}))))

    assert projects == {"projects": [{"id": "project", "label": "Project"}]}
    assert listing["entries"][0]["name"] == "hello.txt"
    assert metadata["kind"] == "text"
    assert preview["content"] == "hello world"
    paths = {getattr(route, "path", None) for route in dashboard_app.routes}
    assert {
        "/api/capabilities", "/api/files/projects", "/api/files/list",
        "/api/files/meta", "/api/files/preview", "/api/files/raw",
        "/api/files/download", "/api/files/content",
    } <= paths


def test_graph_and_session_files_use_universal_viewer_and_pointer_drag_detection():
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    floating = js.split("async function loadFloatingPanelContent", 1)[1].split("function openFloatingSessionPanel", 1)[0]
    session = js.split("async function previewSessionFile", 1)[1].split("function closeSessionDetail", 1)[0]

    assert "renderUniversalFileViewer(path, body" in floating
    assert "/api/files/content" not in floating
    assert "renderUniversalFileViewer(path, body" in session
    assert "/api/files/content" not in session
    assert "_dragPointerStartX = e.clientX" in js
    assert "_dragPointerStartY = e.clientY" in js
    assert "Math.abs(e.clientX - startX)" in js
