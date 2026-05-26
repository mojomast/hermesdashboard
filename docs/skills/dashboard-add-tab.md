---
name: dashboard-add-tab
description: Add a brand-new Hermes Dashboard tab end-to-end with nav/mobile buttons, panel DOM, hash routing, lazy loading, backend APIs when needed, regression tests, and smoke verification.
tags: [dashboard, tabs, starlette, single-file-frontend, testing, navigation]
related_skills: [dashboard-route-nav-patching, dashboard-games-watch-integration]
---

# Dashboard Add Tab

Use when the user asks to add a new tab/panel to the Hermes Dashboard, not merely rename or repair an existing tab.

## Bounded vocabulary

- **Tab id / panel id stem**: kebab-case internal id, e.g. `agent-observability`. The panel DOM id is `${tab_id}-panel`.
- **Tab label**: short user-facing label in desktop and mobile nav, e.g. `Agent Ops`.
- **Hash route**: browser route `#${tab_id}` handled by `handleHashChange()`.
- **Panel**: `<div class="panel" id="${tab_id}-panel">...</div>` inside `templates/index.html`.
- **Lazy loader**: JS function called once from the `switch(panel)` block when the tab is first opened; dynamic panels usually refresh on revisit too.
- **Backend endpoint**: optional Starlette `Route(...)` in `app.py`, usually `/api/<tab-id>`.
- **Regression test**: focused pytest file under `tests/` that asserts every wiring surface exists.

## Current repository shape

The active Hermes Dashboard is a mostly single-file app at:

```text
~/.hermes/dashboard/
├── app.py                  # Starlette backend + API routes
├── templates/index.html    # single-file HTML/CSS/JS frontend
└── tests/                  # pytest regression tests
```

There is no npm frontend build step for this repo unless a future refactor adds one. Prefer `python -m pytest` and, when app.py changed, `python -m py_compile app.py`.

## Procedure

1. **Frame the tab before editing**
   - Pick one canonical `tab_id` in kebab-case.
   - Pick one short label.
   - Decide if the tab is static HTML, dynamic frontend-only, or backend-backed.
   - Decide if an old hash/route alias must be preserved.

2. **Inspect adjacent patterns first**
   ```bash
   cd ~/.hermes/dashboard
   grep -n "data-panel=\"diagnostics\"\|validPanels\|DASHBOARD_TABS\|updateBreadcrumbs\|switch(panel)" templates/index.html
   grep -n "Route(\"/api" app.py
   ```
   Copy the closest existing tab pattern instead of inventing a new one.

3. **Patch `templates/index.html` desktop and mobile nav**
   Add both:
   ```html
   <button class="tab" data-panel="<tab_id>"><Label></button>
   <button class="mobile-tab" data-panel="<tab_id>" onclick="navigateTo('<tab_id>')"><Label></button>
   ```

4. **Patch the dashboard tab registry**
   Add an entry to `DASHBOARD_TABS`:
   ```js
   { id: '<tab_id>', label: '<Label>' },
   ```
   This keeps the Settings/hidden-tabs machinery aware of the tab. Do not rely only on static buttons.

5. **Add the panel DOM**
   Add a sibling panel inside `.container`:
   ```html
   <div class="panel" id="<tab_id>-panel">
       <h2><Label></h2>
       <div id="<tab_id>-status" class="status info">Ready.</div>
       <div id="<tab_id>-content"></div>
   </div>
   ```
   Reuse existing CSS classes where possible. Avoid giant inline bespoke CSS unless the tab needs a distinct layout.

6. **Register hash routing and breadcrumbs**
   In `handleHashChange()`, add `'<tab_id>'` to `validPanels`.

   In `updateBreadcrumbs()`, add the label to the `names` object:
   ```js
   '<tab_id>':'<Label>'
   ```

7. **Add a loader only when the panel needs data**
   Define a JS loader near related panel functions:
   ```js
   async function load<TabName>() {
       const target = document.getElementById('<tab_id>-content');
       if (!target) return;
       target.innerHTML = '<div class="loading">Loading...</div>';
       try {
           const data = await fetchJsonOrThrow('/api/<tab_id>');
           target.innerHTML = render<TabName>(data);
       } catch (error) {
           target.innerHTML = `<div class="error">${escapeHtml(error.message || String(error))}</div>`;
       }
   }
   ```
   Then add it to the lazy-load switch:
   ```js
   case '<tab_id>': load<TabName>(); break;
   ```
   If fresh data is expected on each revisit, add an `else if (panel === '<tab_id>') { load<TabName>(); }` branch after the lazy-load block.

8. **Add backend endpoint only if needed**
   In `app.py`, define the handler near related handlers and add a route near related routes:
   ```python
   async def get_<tab_slug>_endpoint(request):
       return JSONResponse({"ok": True})

   Route("/api/<tab_id>", get_<tab_slug>_endpoint),
   ```
   Keep endpoint output small, deterministic, and easy to test. For filesystem/process state, isolate logic in pure helper functions and test those separately.

9. **Add a regression test before declaring done**
   For navigation-only tabs, create `tests/test_<tab_slug>_panel_navigation.py`:
   ```python
   from pathlib import Path

   TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.html"

   def test_<tab_slug>_tab_is_registered_with_hash_router_and_breadcrumbs():
       html = TEMPLATE.read_text(encoding="utf-8")
       assert 'data-panel="<tab_id>"' in html
       assert 'id="<tab_id>-panel"' in html
       assert "{ id: '<tab_id>', label: '<Label>' }" in html
       assert "'<tab_id>'" in html.split("const validPanels =", 1)[1].split(";", 1)[0]
       assert "'<tab_id>':'<Label>'" in html or "<tab_id>:'<Label>'" in html
   ```
   For backend-backed tabs, also import `app` with the existing Starlette stubs pattern from neighboring tests and assert the route path plus endpoint payload.

10. **Verify locally**
    ```bash
    cd ~/.hermes/dashboard
    python -m py_compile app.py
    python -m pytest -q tests/test_<tab_slug>_panel_navigation.py
    python -m pytest -q
    ```
    If protected `/api/*` smoke tests are needed from a live dashboard, fetch `/` first, extract `window.__HERMES_SESSION_TOKEN__`, and send it as `X-Hermes-Session-Token`.

11. **Runtime refresh**
    If `app.py` or templates changed and a dashboard is already running, restart the dashboard process or tell the user a hard refresh/restart is needed. Browser cache can otherwise show the previous single-file template.

## Pitfalls

- Adding only the visible `<button>` is insufficient; the hash router `validPanels` can still reject the tab.
- Adding only the panel DOM is insufficient; `DASHBOARD_TABS` controls settings/visibility state.
- Desktop and mobile nav are separate blocks; keep both in sync.
- Dynamic tabs need both a lazy-loader switch entry and an endpoint route; one without the other creates silent empty panels or 404s.
- Avoid using `localStorage` for bulky state. Use `/api/dashboard-state/{conversation|active_run}` patterns or a new server-side persistence endpoint when state must survive reloads.
- Do not commit generated `__pycache__`, `.pytest_cache`, runtime SQLite DBs, logs, or watch-server scratch files.

## Completion report

Report:

- tab id and label,
- panel DOM and route surfaces patched,
- backend endpoint(s), if any,
- regression test file(s),
- verification commands and results,
- whether running dashboard needs restart/hard refresh.
