---
name: dashboard-route-nav-patching
description: Fix Hermes Dashboard tab/route mismatches by tracing nav labels, route aliases, and title/header resolution together, then verifying both frontend build and backend API smoke checks.
---

# Dashboard Route/Nav Patching

## When to use

Use this when a Hermes Dashboard tab, sidebar/nav item, or page header does not match the intended route, e.g. clicking a tab keeps showing another page, the URL changes but the header does not, or an old route name needs to remain as an alias.

## Approach

1. **Map the vocabulary first**
   - Identify the user-facing tab label.
   - Identify the canonical route path.
   - Identify any backward-compatible aliases that should still work.
   - Identify the page title/header resolver path, if separate from routing.

2. **Patch all route surfaces together**
   - Update the nav item/link target to the canonical route.
   - Add or preserve aliases for old URLs when existing users/bookmarks may depend on them.
   - Update route-to-title/header resolution so the visual page name matches both canonical and alias paths.
   - Check for duplicated route constants or hard-coded labels in both frontend and backend code.
   - For the active dashboard at `~/.hermes/dashboard`, inspect the nav partials, panel partial, and `static/js/dashboard.js` together: a tab may have `data-panel="name"` and an existing `id="name-panel"`, but still fail because `handleHashChange()` has a separate `validPanels` allowlist. Add the panel to that allowlist, `DASHBOARD_TABS`, and the breadcrumb `names` map, then add a regression test like `tests/test_<panel>_panel_navigation.py` asserting the nav button, panel id, router allowlist entry, lazy-loader case, and breadcrumb label. Also decide whether the tab belongs in `DEFAULT_VISIBLE_DASHBOARD_TABS` or should remain hidden-by-default with an experimental warning.

3. **Prefer compatibility over renaming-only fixes**
   - If replacing `/old-name` with `/new-name`, keep `/old-name` as an alias unless there is a strong reason to remove it.
   - Make the nav label precise and user-facing; do not rely on internal component names.

4. **Verify in two layers**
   - Run the relevant local verification. This repo currently has no npm frontend build step; use `python3 -m pytest`, `python3 -m py_compile app.py` when Python changed, and `node --check static/js/dashboard.js` when JavaScript changed.
   - Smoke-test at least one relevant backend/API route used by the page, especially if backend title/route helpers were touched.
   - If a dashboard server was already running, restart it for backend Python changes or changed frontend assets. For Hermes dashboard on the default local port, identify the process with `ss -ltnp` / `ps`, stop only the dashboard PID, then relaunch from the repo, e.g. `/home/mojo/.local/bin/hermes dashboard --no-open --port 9119`.
   - Protected `/api/*` dashboard endpoints may return `401` to raw smoke tests. Fetch the HTML route first, extract `window.__HERMES_SESSION_TOKEN__`, and send it as `X-Hermes-Session-Token` when smoking the API.

## Pitfalls

- Fixing only the visible nav label can leave the click target or route resolver stale.
- Fixing only the frontend route can leave backend-driven headers/titles showing the old page.
- Removing an old route may break existing browser tabs or saved dashboard state; prefer aliases.
- Passing local tests does not prove backend route/title helpers were reloaded in an already-running dashboard; smoke-test the API and mention restart if needed.

## Minimal completion report

Report:

- canonical route installed,
- aliases preserved,
- nav label/page header behavior,
- verification command result,
- API smoke-test result,
- whether the running dashboard server needs restart or browser hard refresh.
