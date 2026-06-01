# Hermes Dashboard refactor map

This copy is the safe refactor target for the dashboard monolith. The original dashboard directories must remain untouched.

## Current monolith shape

- `app.py` owns the Starlette application, route table, backend API handlers, proxy handlers, persistence helpers, and dashboard template rendering.
- `templates/index.html` owns the visible dashboard markup and previously embedded all dashboard CSS and JavaScript inline.
- Static frontend assets now live under `static/` and are served from `/static` by Starlette `StaticFiles`.

## First safe pass completed/targeted

1. Keep backend behavior and route contracts unchanged except for adding the `/static` mount.
2. Extract only mechanical frontend assets:
   - `static/css/dashboard.css` contains the previous full inline `<style>` block from `templates/index.html`.
   - `static/js/dashboard.js` contains the previous full main dashboard inline script from the bottom of `templates/index.html`.
3. Load `dashboard.js` as a classic deferred script, not an ES module, so existing inline `onclick` handlers and global function lookups continue to work.
4. Leave third-party CDN assets in the template for now.
5. Update focused tests that inspect raw template/source text so they intentionally include extracted static assets where appropriate.

## Backend extraction pass completed

- `dashboard_backend/services/dashboard_state.py` now owns dashboard-state SQLite schema creation and load/save/delete persistence.
- `app.py` keeps compatibility wrappers (`_load_dashboard_state`, `_save_dashboard_state`, etc.) that pass live `DASHBOARD_STATE_DB_PATH`, `DASHBOARD_STATE_LOCK`, and `DASHBOARD_STATE_KEYS` into the service so existing monkeypatch-based tests and callers keep working.
- Targeted regression gate: `python -m pytest tests/test_dashboard_state_persistence.py`.

## Backend follow-up plan

- Split `app.py` by stable bounded contexts without changing public API paths:
  - application/bootstrap and route registration
  - dashboard state persistence
  - sessions/files/memory/skills/games APIs
  - diagnostics and execution trace APIs
  - autonomous development/self-improvement/scrolls APIs
  - D&D campaign APIs
  - proxy integrations (`doom`, `minihack`, `pokemon`)
- Add route-registration tests before each extraction to compare the route table before/after each move.
- Prefer small modules with pure helpers first, then endpoint moves once imports and monkeypatch seams are clear.

## Frontend follow-up plan

- Keep globals stable while extracting by feature area; avoid `type="module"` until inline handlers are removed or explicitly bridged.
- Add a small asset-source helper for tests that need to inspect dashboard markup plus extracted CSS/JS.
- Move feature-specific JavaScript into namespace-like classic scripts only after dependencies are mapped.
- Replace inline event handlers with delegated listeners in later passes, then consider modules/bundling.

## Guardrails

- Do not modify `/home/mojo/.hermes/dashboard` or `/home/mojo/.hermes/repos/hermesdashboard`.
- Preserve existing route paths, response payload shapes, and dashboard global function names.
- Run `python -m py_compile app.py` and `python -m pytest` after each pass.
