from pathlib import Path
import subprocess

from tests.dashboard_sources import DASHBOARD_CSS, DASHBOARD_JS, dashboard_template


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "static" / "vendor" / "xterm"


def test_terminal_uses_body_host_inert_template_and_shared_accessible_auth():
    html = dashboard_template()

    container_close = html.index("</div>", html.index('<div class="container">'))
    host = html.index('id="terminal-window-host"')
    template = html.index('id="terminal-window-template"')
    assert host > container_close
    assert template > host
    assert 'data-terminal-role="window"' in html
    assert 'data-terminal-role="screen"' in html
    assert 'role="dialog" aria-modal="false"' in html
    assert 'aria-controls="terminal-window-host"' in html
    assert 'aria-label="New terminal, 0 open"' in html
    assert 'id="terminal-launcher-count"' in html
    assert 'id="terminal-launcher-status"' in html
    assert 'id="terminal-dock"' in html
    assert 'aria-label="Open terminals"' in html
    assert 'id="dashboard-workspace"' in html
    assert 'id="terminal-column"' in html
    assert 'id="terminal-column-stack"' in html
    assert 'id="terminal-column-resizer"' in html
    assert 'data-terminal-role="dock"' in html
    assert 'aria-pressed="false"' in html
    assert 'id="terminal-auth" role="dialog" aria-modal="true"' in html
    assert html.count('id="terminal-access-token"') == 1
    assert 'autocomplete="off"' in html
    assert 'id="terminal-window"' not in html
    assert 'id="terminal-screen"' not in html


def test_terminal_uses_pinned_local_classic_xterm_assets_lazily():
    html = dashboard_template()
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "/static/vendor/xterm/" not in html
    assert "xterm@" not in html
    assert "const XTERM_VERSION = '5.3.0'" in js
    assert "const FIT_VERSION = '0.8.0'" in js
    assert "/static/vendor/xterm/xterm.js" in js
    assert "/static/vendor/xterm/xterm.css" in js
    assert "/static/vendor/xterm/xterm-addon-fit.js" in js
    assert "document.createElement('script')" in js
    assert "new window.Terminal" in js
    assert "new window.FitAddon.FitAddon" in js
    assert (VENDOR / "xterm.js").stat().st_size > 250_000
    assert (VENDOR / "xterm.css").stat().st_size > 5_000
    assert (VENDOR / "xterm-addon-fit.js").stat().st_size > 1_000


def test_terminal_manager_transport_auth_and_error_contracts():
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "class BrowserTerminalManager" in js
    assert "class TerminalWindowController" in js
    assert "this.controllers = new Map()" in js
    assert "fetch('/api/terminal/status'" in js
    assert "fetch('/api/terminal/auth'" in js
    assert "new URL('/api/terminal/ws'" in js
    assert "url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'" in js
    assert "candidate.binaryType = 'arraybuffer'" in js
    assert "this.socket === candidate" in js
    assert "this.socket !== candidate" in js
    assert "this.sendControl({ type: 'input', data })" in js
    assert "type: 'resize', cols: this.terminal.cols, rows: this.terminal.rows" in js
    assert "closingSocket.send(JSON.stringify({ type: 'close' }))" in js
    assert "this.terminal?.dispose()" in js
    assert "event.code === 4429" in js
    assert "event.code === 4404" in js
    assert "event.code === 4403" in js
    assert "this.manager.handleAuthRequired(this)" in js
    assert "if (this.authPromise) return this.authPromise" in js
    assert "body: JSON.stringify({ token })" in js


def test_terminal_geometry_window_and_theme_contracts():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "const STORAGE_KEY = 'hermes_terminal_windows_v2'" in js
    assert "const LEGACY_STORAGE_KEY = 'hermes_terminal_window_v1'" in js
    assert "const SESSION_STORAGE_KEY = 'hermes_terminal_sessions_v1'" in js
    assert "slots: this.geometrySlots" in js
    assert "this.geometrySlots.slice(0, this.maxSessions)" in js
    assert "this.usedSlots.delete(slot)" in js
    assert "new ResizeObserver" in js
    assert "window.addEventListener('resize', this.handleViewportResize)" in js
    assert "this.bodyEl.inert = minimized" in js
    assert "['keydown', 'keyup', 'keypress']" in js
    assert "attachCustomKeyEventHandler" in js
    assert "this.terminal?.hasSelection?.()" in js
    assert "navigator.clipboard.writeText(selection)" in js
    assert "navigator.clipboard.readText()" in js
    assert "this.terminal?.paste(text)" in js
    assert "window.innerWidth - MIN_WORKSPACE_WIDTH" in js
    assert "this.controllers.forEach(controller => controller.applyTheme(theme))" in js
    assert "controller.setDocked(true, false)" in js
    assert "this.manager.columnStackEl?.appendChild(this.windowEl)" in js
    assert "this.manager.hostEl.appendChild(this.windowEl)" in js
    assert "this.docked" in js
    assert ".terminal-window" in css
    assert "z-index: 20000" in css
    assert "resize: both" in css
    assert ".terminal-window.is-minimized" in css
    assert ".terminal-window.is-maximized" in css
    assert '[data-theme="light"] .terminal-screen' in css
    assert "touch-action: none" in css
    assert ".terminal-launcher.at-limit" in css
    assert ".terminal-dock-item" in css
    assert ".terminal-window.is-minimized {\n    display: none;" in css
    assert ".dashboard-workspace" in css
    assert ".terminal-column-stack" in css
    assert ".terminal-window.is-docked" in css
    assert "max-width: calc(100vw - 320px)" in css
    assert "flex-direction: column" in css


def test_terminal_multi_window_behavior_in_node_fake_dom():
    result = subprocess.run(
        ["node", str(ROOT / "tests" / "terminal_frontend_harness.js"), str(DASHBOARD_JS)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "terminal frontend harness: ok" in result.stdout
