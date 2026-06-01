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

## Backend extraction passes completed

- `dashboard_backend/services/dashboard_state.py` owns dashboard-state SQLite schema creation and load/save/delete persistence.
  - `dashboard_backend/routes/dashboard_state.py` owns `/api/dashboard-state/{key}` request parsing, JSON response envelopes, and `ValueError` to `404` mapping.
  - `app.py` keeps compatibility wrappers (`_load_dashboard_state`, `_save_dashboard_state`, etc.) plus app-level endpoint names (`get_dashboard_state`, `set_dashboard_state`, `delete_dashboard_state`) that pass live `DASHBOARD_STATE_DB_PATH`, `DASHBOARD_STATE_LOCK`, and `DASHBOARD_STATE_KEYS` into the service so existing monkeypatch-based tests and callers keep working.
  - Targeted regression gate: `python -m pytest tests/test_dashboard_state_persistence.py tests/test_dashboard_state_routes.py`.
- `dashboard_backend/services/token_usage.py` owns token usage constants, read-only aggregation helpers, and token/cost projection construction.
  - `app.py` keeps compatibility wrappers (`_empty_token_usage_window`, `_token_usage_total`, `_aggregate_token_usage_api_calls`, `_aggregate_token_usage_sessions`, `get_token_usage_summary`) and the `/api/token-usage` route wrapper.
  - Targeted regression gate: `python -m pytest tests/test_token_usage_dashboard.py`.
- `dashboard_backend/services/message_board.py` owns message-board SQLite post/message persistence.
  - `app.py` keeps compatibility wrappers for public/private message-board helper names, plus the `/api/message-board*` route handlers and Hermes agent-reply generation.
  - Targeted regression gate: `python -m pytest tests/test_message_board.py`.
- `dashboard_backend/services/scrolls.py` owns the read-only Scrolls snapshot state projection delegation to the standalone Vesuvius `research_dashboard` package.
  - `app.py` keeps the `/api/scrolls/snapshot` route wrapper and passes `_SCROLLS_PROJECT_ROOT` into the service at call time.
  - Targeted regression gate: `python -m pytest tests/test_scrolls_snapshot.py tests/test_scrolls_panel_navigation.py`.
- `dashboard_backend/services/games_catalog.py` owns the read-only Games tab skill catalog/frontmatter projection.
  - `app.py` keeps the `/api/games` route wrapper plus compatibility helper names, and passes live `HERMES_HOME` into the service at call time.
  - Targeted regression gate: `python -m pytest tests/test_games_catalog_service.py tests/test_games_tab.py`.
- Self-improvement repair/anomaly parity restored bounded read-only event-coverage projections.
  - `app.py` surfaces `repair_hint` / `event_coverage_repair_hint` without adding mutation routes.
  - `static/js/dashboard.js` renders Repair Readiness, Anomaly Samples, and inert Next repair commands while the tab remains hidden-by-default.
  - Targeted regression gate: `python -m pytest tests/test_self_improvement_panel.py`.

## Backend follow-up plan

- Split `app.py` by stable bounded contexts without changing public API paths:
  - application/bootstrap and route registration
  - dashboard state persistence and route-wrapper parsing/envelopes
  - sessions/files/memory/skills/games APIs
  - diagnostics and execution trace APIs
  - autonomous development/self-improvement/scrolls APIs
  - D&D campaign APIs
  - proxy integrations (`doom`, `minihack`, `pokemon`)
- Add route-registration tests before each extraction to compare the route table before/after each move.
- Prefer small modules with pure helpers first, then endpoint moves once imports and monkeypatch seams are clear.
- Keep `app.py -> routes -> services -> core` as the dependency direction; route modules parse `Request` objects and delegate to services, while services never import `app.py`.

## Frontend template partial pass completed

- `templates/index.html` is now a Jinja shell that includes dashboard partials from `templates/dashboard/partials/`.
- Shell/navigation partials own head assets, top navigation, mobile navigation, modal overlays, the session drawer, and the classic dashboard script tag.
- Panel markup moved to `templates/dashboard/partials/panels/` with one file per dashboard panel while preserving panel IDs and `data-panel` values.
- Tests now render the Jinja template before inspecting dashboard markup, then concatenate extracted CSS/JS for source-contract checks.
- Compatibility constraints remain: `/static/js/dashboard.js` is still a classic deferred script, `type="module"` is not used, and inline handler globals are preserved.

## Frontend follow-up plan

- Keep globals stable while extracting by feature area; avoid `type="module"` until inline handlers are removed or explicitly bridged.
- CSS next safest pass: mechanically split order-preserving static imports, starting with self-contained/bracketed blocks such as graph, command palette, interrupt, token-cost, and D&D styles.
- JavaScript next safest pass: map hoisting/initialization first and move top-level boot into a final classic bootstrap script before splitting feature files.
- Replace inline event handlers with delegated listeners in later passes, then consider modules/bundling.

## Frontend parity pass completed

- Restored chat image attachment/paste controls in the refactored chat panel, CSS, JavaScript rendering/sending path, and backend chat-message sanitizer.
- Restored the dirty reference's frontend-only Roguelike/Hermes Labyrinth tab as an experimental hidden-by-default panel with partialized HTML, extracted CSS/JS, and no backend API route.
- New installs now default to a safer tab set: chat, message board, config, secrets, sessions, memory, skills, cron, schedule, and graph.
- Local-tooling-specific tabs remain registered and can be enabled from dashboard settings with experimental warnings: agent observability, games, roguelike, diagnostics, D&D campaigns, self-improvement, autonomous development, and Vesuvius AutoResearch.
- Existing users with an explicit `hermes_dashboard_hidden_tabs_v1` localStorage value keep their customized visibility; only browsers with no stored preference receive the safer defaults.

## Guardrails

- Do not modify `/home/mojo/.hermes/dashboard` or `/home/mojo/.hermes/repos/hermesdashboard`.
- Preserve existing route paths, response payload shapes, and dashboard global function names.
- Run `python -m py_compile app.py`, `node --check static/js/dashboard.js`, and `python -m pytest` after each pass.
