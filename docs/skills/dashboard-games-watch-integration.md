---
name: dashboard-games-watch-integration
description: Add a new watchable game to Hermes Dashboard Games tab using gaming skill metadata, local watch server, dashboard proxy routes, tests, and smoke verification.
tags: [dashboard, games, skills, proxy, watch-server, starlette, testing]
---

# Dashboard Games Watch Integration

Use when adding a new game card to Hermes Dashboard **Games** that opens a local watch server inside the dashboard iframe.

## Trigger

The user asks to add a new game to the Games tab, or to make a game watchable from the dashboard.

## Bounded contexts / vocabulary

- **Game skill**: `~/.hermes/skills/gaming/<game-id>/SKILL.md`; the Games catalog discovers these.
- **Watch server**: local process bound to `127.0.0.1:<high-port>` serving a browser UI plus status endpoints.
- **Dashboard proxy**: Starlette routes in `~/.hermes/dashboard/app.py` that proxy `/game-prefix/` to the local watch server so remote browsers do not connect to their own localhost.
- **Watch URL**: same-origin dashboard path, e.g. `/doom/` or `/minihack/`, not `http://127.0.0.1:port/`.

## Procedure

1. Inspect existing patterns first:
   ```bash
   cd ~/.hermes/dashboard
   grep -n "DOOM_WATCH\|doom_watch_proxy\|/doom" app.py tests/test_games_tab.py
   ```
   Prefer copying the Doom pattern unless the new server has special rewrite needs.

2. Create the gaming skill:
   ```text
   ~/.hermes/skills/gaming/<game-id>/SKILL.md
   ~/.hermes/skills/gaming/<game-id>/scripts/<game>_watch_server.py
   ```

3. Use dashboard frontmatter like:
   ```yaml
   ---
   name: minihack-player
   description: Watch Hermes crawl MiniHack/NetHack dungeon tasks from the dashboard.
   tags: [gaming, minihack, nethack, roguelike, watch, benchmark]
   dashboard:
     watch_url: /minihack/
     launch_label: Watch Hermes Crawl Dungeons
     status_hint: Run the MiniHack watch server, then click Watch from the Games tab.
   ---
   ```

4. Watch server design:
   - Bind to `127.0.0.1` only.
   - Use a high port (`9988+`; avoid known occupied 3000/3001 and project ports).
   - Serve `/` HTML and `/status.json`; add `/learning.json` when useful.
   - Include a no-dependency or graceful fallback mode when optional game deps are missing, so dashboard wiring can still be smoke-tested.
   - Persist learning/benchmark files beside the skill only at runtime; remove generated files before reporting/committing unless intentionally keeping them.

5. Add dashboard proxy in `~/.hermes/dashboard/app.py`:
   - Add env var near Doom/Pokemon constants:
     ```python
     MINIHACK_WATCH_SERVER_URL = os.getenv("HERMES_MINIHACK_WATCH_URL", "http://127.0.0.1:9989")
     ```
   - Add an async proxy endpoint using `httpx.AsyncClient(timeout=None)` and `StreamingResponse`.
   - Add friendly 502 text with the exact start command.
   - If the upstream HTML uses root-absolute URLs like `/status.json`, either make the watch server use relative URLs (`status.json`) or add a rewrite helper like Doom’s `_rewrite_doom_watch_html`.
   - Add routes:
     ```python
     Route("/minihack/", minihack_watch_proxy_endpoint, methods=["GET", "POST"]),
     Route("/minihack/{path:path}", minihack_watch_proxy_endpoint, methods=["GET", "POST"]),
     ```

6. Add/update tests in `~/.hermes/dashboard/tests/test_games_tab.py`:
   - Catalog test asserting `category == "Watch"`, `watch_url`, `launch_label`, and `status_hint` from skill frontmatter.
   - Route assertions for `/minihack/` and `/minihack/{path:path}`.
   - Rewriter tests only if HTML rewriting is needed.

7. Verify:
   ```bash
   python3 -m py_compile ~/.hermes/skills/gaming/<game-id>/scripts/<game>_watch_server.py ~/.hermes/dashboard/app.py
   cd ~/.hermes/dashboard
   PYTHONPATH=. python3 -m pytest -q tests/test_games_tab.py
   ```

8. Smoke-test the server on a temporary high port:
   ```bash
   ~/.hermes/skills/gaming/<game-id>/scripts/<game>_watch_server.py --host 127.0.0.1 --port 9997
   python3 - <<'PY'
   import json, urllib.request
   for path in ['/', '/status.json']:
       data = urllib.request.urlopen('http://127.0.0.1:9997'+path, timeout=5).read()
       print(path, len(data), data[:100])
   PY
   ```
   Kill the smoke process afterwards.

## Pitfalls

- Do not put `http://127.0.0.1:<port>/` in skill `watch_url`; remote dashboard users would connect to their own machine. Use a dashboard proxy path.
- Avoid root-absolute asset/status URLs inside watch-server HTML unless the dashboard proxy rewrites them.
- `py_compile` can create `__pycache__`; remove generated cache/runtime files before final status if they are not meant to be kept.
- `git diff` in dashboard may include unrelated dirty work. Report only the files touched for the game integration and avoid committing unrelated changes.
- `fetch_url` may fail if `trafilatura` is missing; use direct `urllib`/`~/duck-search.py` for lightweight research when needed.

## Example: MiniHack outcome

For `minihack-player`, the reusable pattern was:

- Skill metadata with `watch_url: /minihack/`.
- Local `scripts/minihack_watch_server.py` with `/`, `/status.json`, `/learning.json`.
- No-dependency procedural demo fallback when MiniHack/NLE are not installed.
- Dashboard env var `HERMES_MINIHACK_WATCH_URL` defaulting to `http://127.0.0.1:9989`.
- Proxy routes `/minihack/` and `/minihack/{path:path}`.
- Focused verification: `tests/test_games_tab.py` passed and smoke endpoints returned live status.
