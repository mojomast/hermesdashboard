# Hermes Dashboard

This directory contains the local Hermes dashboard app and a helper for running a chat-only Hermes API server.

## Files

- `app.py`: Starlette dashboard backend
- `templates/index.html`: single-file dashboard frontend
- `run_api_server_only.py`: isolated Hermes API server launcher for dashboard chat
- `docs/skills/`: vendored Hermes dashboard-editing skills/checklists for contributors

## Dashboard Editing Skills

Before adding or repairing dashboard tabs, read the relevant vendored skill:

- `docs/skills/dashboard-add-tab.md` for brand-new tabs/panels
- `docs/skills/dashboard-route-nav-patching.md` for route/nav/breadcrumb mismatches
- `docs/skills/dashboard-games-watch-integration.md` for Games tab watch-server integrations

## Runtime Layout

- Dashboard UI: `http://127.0.0.1:8081`
- Hermes chat API: `http://127.0.0.1:8642`
- Remote dashboard URL currently used by the user: `https://kimi.tailec998.ts.net/`

`app.py` proxies browser chat requests to the Hermes API at `127.0.0.1:8642`.

## Why `run_api_server_only.py` exists

The full Hermes gateway process tries to start all enabled/ad-hoc platform adapters from config and env.
In this environment, `TELEGRAM_BOT_TOKEN` and `DISCORD_BOT_TOKEN` in `~/.hermes/.env` can make gateway restarts noisy or unreliable for dashboard-only work.

`run_api_server_only.py` starts only `gateway.platforms.api_server.APIServerAdapter` so dashboard chat can work without the rest of the messaging gateway.

Recommended way to run it:

```sh
nohup env -u TELEGRAM_BOT_TOKEN -u DISCORD_BOT_TOKEN \
  API_SERVER_ENABLED=true \
  API_SERVER_HOST=127.0.0.1 \
  API_SERVER_PORT=8642 \
  API_SERVER_KEY=hermes-dashboard-secret-9e4349ef052042545dd435d3330a2287 \
  /home/mojo/.hermes/hermes-agent/venv/bin/python \
  /home/mojo/.hermes/dashboard/run_api_server_only.py \
  >/tmp/hermes-api-only.log 2>&1 &
```

Recommended way to run the dashboard:

```sh
nohup sh -c 'set -a && . /home/mojo/.hermes/.env && set +a && exec /home/mojo/.hermes/hermes-agent/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8081' \
  >/tmp/hermes-dashboard.log 2>&1 &
```

## Important Endpoints

Dashboard backend routes in `app.py`:

- `GET /`: dashboard page
- `POST /chat`: SSE proxy to Hermes `/v1/chat/completions`
- `GET /api/status`
- `GET /api/config`
- `GET /api/settings`
- `POST /api/config`
- `GET /api/models`
- `GET /api/personalities`
- `GET /api/secrets`
- `POST /api/secrets`
- `DELETE /api/secrets/{key}`
- `GET /api/sessions` — supports `?limit=`, `?offset=`, `?search=`, `?sort=date_desc|date_asc`, `?source=`
- `GET /api/sessions/sources` — returns distinct session sources for filter dropdown
- `POST /api/sessions/backfill-summaries` — backfill persisted summaries for historical sessions
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/summary` — regenerate a single session summary
- `GET /api/sessions/{session_id}/files`
- `DELETE /api/sessions/{session_id}`
- `GET /api/files/content?path=...`
- `GET /api/memory`
- `POST /api/memory`
- `GET /api/skills`
- `POST /api/skills/toggle`
- `GET /api/skills/{skill_id}/content` — returns full SKILL.md content and file listing
- `GET /api/graph?depth=full|shallow&hours=24|168|720|0|all`

Hermes API routes used by the dashboard:

- `GET /health`
- `POST /v1/chat/completions`

## Chat Stream Format

The browser consumes a simplified SSE event stream from `POST /chat`.

Event types currently forwarded by the dashboard proxy:

- `{"type":"content","content":"..."}`
- `{"type":"tool_call", ...}`
- `{"type":"tool_output", ...}`
- `{"type":"tool_progress", ...}` — delegation subagent progress batches and nested delegate stream updates
- `{"type":"run_state","session_id":"..."}` — session ID assignment at run start
- `{"type":"meta", "usage": {...}, "last_prompt_tokens": ..., "prompt_breakdown": [...]}`
- `[DONE]`

The API server now also emits periodic heartbeat-style `meta` chunks during idle long-running work so the dashboard proxy does not time out while subagents are active.

The frontend must buffer SSE reads by blank-line event boundaries and handle both LF and CRLF line endings. Do not assume each `reader.read()` returns complete lines or complete JSON payloads.

The dashboard frontend now reduces both live SSE events and historical session rows through the same assistant-step trace model.

Important implications:

- top-level tool matching should be driven by canonical `call_id`, not tool-name heuristics
- unmatched top-level tool outputs/progress should stay visible as orphan diagnostics rather than being silently attached to the wrong tool
- floating session panels must scope transcript DOM ids so deep-link targets still resolve to the main session detail transcript correctly

## Prompt Breakdown

Hermes now includes prompt breakdown metadata so the dashboard can inspect why prompt tokens are large.

Each breakdown item may include:

- `name`
- `chars`
- `estimated_tokens`
- `source`
- `count`
- `content`

`content` is the important troubleshooting field. It contains the actual injected prompt section text, including items like:

- `identity`
- `tool_guidance`
- `memory`
- `user_profile`
- `skills`
- `conversation_history`
- `tool_schemas`

## API Server Tool Surface

The dashboard chat API is intentionally lean by default.

`api_server` currently loads only the core chat toolsets from `config.yaml`:

- `web`
- `terminal`
- `file`
- `skills`
- `todo`
- `memory`
- `session_search`
- `code_execution`
- `delegation`

Heavy or specialized toolsets are not loaded into every dashboard chat prompt by default:

- browser automation
- vision
- image generation
- cronjob
- mixture of agents
- Home Assistant
- Honcho
- MCP servers such as `becomussy`

This is deliberate: `tool_schemas` was dominating prompt size, and MCP servers can add dozens of tools to every turn.

## Delegation-Only Heavy Tools

Heavy toolsets are still available on demand through `delegate_task`.

In this setup, `delegation.allowed_toolsets` includes:

- `becomussy`
- `browser`
- `vision`
- `image_gen`
- `cronjob`
- `moa`
- `honcho`
- `homeassistant`

That means the parent dashboard/API chat stays lean, but Hermes can spawn a subagent with one of those toolsets when needed. Example pattern:

- use `delegate_task(..., toolsets=["becomussy"])` for continuity or MCP-backed memory work
- use `delegate_task(..., toolsets=["browser"])` for browser automation

The heavy schemas only appear in the delegated child prompt, not every top-level chat turn.

## Known Token Findings

On this setup, a fresh chat prompt is dominated by:

- `tool_schemas` (previously `~11k+` tokens before the lean `api_server` tool surface)
- `skills` (`~2.4k` tokens)

Disabling skills from the dashboard originally appeared ineffective because the cached skills snapshot did not invalidate on `config.yaml` changes. That was fixed by including `config.yaml` in the skills snapshot manifest.

If `tool_schemas` jumps unexpectedly again, check for either:

1. extra toolsets added back to `platform_toolsets.api_server`
2. MCP servers explicitly listed under `platform_toolsets.api_server`

## Z.AI Models

`GET /api/models` now queries the Z.AI `/models` endpoint directly using:

- `GLM_API_KEY` or `ZAI_API_KEY` or `Z_AI_API_KEY`
- `GLM_BASE_URL` or `config.model.base_url` or `https://api.z.ai/api/paas/v4`

Fallback list is used only if the direct endpoint call fails.

## Session File Browser

The session detail modal includes a file browser built from persisted tool history in `state.db`.

Currently reconstructed tool activity:

- `read_file`
- `write_file`
- `patch`

Preview is restricted to allowed roots:

- `HERMES_WRITE_SAFE_ROOT` if set
- current working directory
- active `HERMES_HOME`

## Session Summary Behavior

Hermes persists a short session summary in `sessions.summary`.

- Summaries are generated with Gemini 2.5 Flash Lite over OpenRouter through the auxiliary client path
- Auto-generated session titles now reuse the same transcript formatting path as session summaries, with a title-specific prompt layered on top
- Auto-generation is intentionally limited to brand new chats after the first completed exchange
- Existing sessions can be backfilled or regenerated on demand
- The dashboard surfaces summaries in sessions list rows, session detail, graph tooltips, graph sidebar metadata, and floating session panels

If summary regeneration returns `OPENROUTER_API_KEY not set`, the dashboard web process was started without `~/.hermes/.env` loaded.

## Frontend Rendering Notes

The frontend is implemented inside `templates/index.html`.

Important behavior:

- `Chat Context` is collapsible as a whole
- prompt breakdown rows are individually expandable
- assistant messages render as an ordered event timeline
- tool events should appear chronologically, not appended after all content
- tool blocks should collapse to compact single-line rows first and only reveal payload/output details on demand
- chat reloads during an active stream should surface the saved run clearly and let the user explicitly reattach the session or resume the stream

Session detail specifically now renders:

- a session overview block with timing, lineage, token, and cost metadata
- per-message timestamps and finish/token metadata where available
- collapsible reasoning/debug sections for assistant messages
- normalized assistant steps with attached tool runs instead of flat assistant/tool reconstruction
- explicit grouped parallel batches for multi-tool assistant turns
- inline child-session stages and related request-dump diagnostic artifacts
- deep-linkable tool, child-session, and artifact anchors used by side-panel activity items when target metadata exists

Current limitations:

- persisted history still relies on runtime `tool_call_id` quality; missing canonical ids can still produce orphan tool diagnostics
- child-session placement is inline and linked, but not yet tied to a first-class persisted subagent/tool-run record
- request-dump artifacts are attached as diagnostics, not as full event-log replay data
- active-run recovery is browser-local and depends on localStorage; it does not yet query backend run state independently after refresh

## Config Surface

The Config tab now renders from `GET /api/settings` instead of hardcoding a handful of individual controls.

Backend behavior:

- `GET /api/config` returns raw persisted YAML
- `GET /api/settings` returns a dashboard-oriented payload with normalized model config, overview stats, skins, personalities, toolsets, platform metadata, and secret coverage
- `POST /api/config` still applies dotted-path updates into raw config and now defensively converts non-dict parents to dicts when needed

Frontend behavior:

- the Config tab is built dynamically after `loadSettings()`
- save handlers are section-scoped instead of one global config form
- complex groups use JSON editors to avoid lossy field-by-field editing
- platform toolset saves must preserve custom extras such as MCP server names like `becomussy`
- old code that assumes static `provider-select` or `personality-select` DOM nodes at boot is unsafe because those nodes now exist only after the Config tab renders

Current config sections:

- `Model & Routing`
- `Agent & Personality`
- `Memory & Session`
- `Tools & Skills`
- `Browser / Web / Voice`
- `Display & UX`
- `Advanced Admin`

Important memory defaults surfaced in Config:

- `memory.memory_char_limit` default is now `22000`
- `memory.user_char_limit` default is now `13750`

## Secrets Surface

The Secrets tab is metadata-driven.

- primary metadata comes from `hermes_cli.config.OPTIONAL_ENV_VARS`
- dashboard adds a small amount of extra metadata for keys Hermes uses but does not fully describe there
- unknown keys matching `API_KEY`, `TOKEN`, `SECRET`, or `_URL` patterns are still surfaced as advanced items

## Relationship Graph

The Graph tab provides a D3 force-directed graph visualization of relationships between sessions, files, tools, models, and skills.

### Architecture

- **Backend**: `GET /api/graph` in `app.py` assembles nodes and edges from `state.db` and the skills directory
- **Frontend**: D3.js v7 force simulation rendered to HTML5 Canvas inside `templates/index.html`
- Single `<canvas>` element replaces ~9000 SVG DOM elements. Rendering is batched via `requestAnimationFrame`
- HiDPI support: canvas dimensions are scaled by `devicePixelRatio` for crisp rendering on retina displays
- All code is inline in the single-file architecture (no separate JS/CSS files)

### API: `GET /api/graph`

Query parameters:

| Param | Values | Default | Description |
|-------|--------|---------|-------------|
| `depth` | `full`, `shallow` | `full` | `shallow` = sessions + models only. `full` = all node types including files, tools, skills |
| `hours` | number or `all` | `24` | Time scope. `0.5` = 30 min, `1` = 1h, `3` = 3h, `6` = 6h, `12` = 12h, `24` = 24h, `168` = 7 days, `720` = 30 days, `0` or `all` = no filter |

Response:

```json
{
  "nodes": [
    { "id": "session:abc123", "label": "Fix login bug", "type": "session", "model": "glm-5", ... },
    { "id": "file:/home/mojo/app.py", "label": "app.py", "type": "file", "path": "/home/mojo/app.py", ... },
    { "id": "tool:read_file", "label": "read_file", "type": "tool", "usage_count": 42 },
    { "id": "model:glm-5", "label": "glm-5", "type": "model", "session_count": 12 },
    { "id": "skill:github-code-review", "label": "github-code-review", "type": "skill", ... }
  ],
  "edges": [
    { "source": "session:abc123", "target": "file:/home/mojo/app.py", "type": "accessed" },
    { "source": "session:abc123", "target": "tool:read_file", "type": "used_tool" },
    ...
  ],
  "node_count": 354,
  "edge_count": 1430
}
```

### Node Types

| Type | Source | ID Pattern | Shape | Color | Key Properties |
|------|--------|------------|-------|-------|----------------|
| `session` | `sessions` table | `session:<id>` | hexagon | `#a855f7` purple | title, source, model, started_at, ended_at, message_count, tool_call_count, tokens, cost |
| `file` | Extracted from tool_call arguments | `file:<path>` | circle | `#22c55e` green | path, basename, category |
| `tool` | Aggregated from `messages.tool_calls` | `tool:<name>` | diamond | `#f97316` orange | name, usage_count |
| `model` | `sessions.model` column | `model:<name>` | square | `#06b6d4` cyan | name, session_count |
| `skill` | `~/.hermes/skills/<cat>/<name>/SKILL.md` | `skill:<name>` | circle | `#ffd700` gold | name, description, category, enabled |

### Edge Types

| From -> To | Type | Color | How Extracted |
|-----------|------|-------|---------------|
| Session -> File | `accessed` | green | `path`/`file_path` from tool_call arguments |
| Session -> Tool | `used_tool` | orange | `function.name` from `messages.tool_calls` JSON |
| Session -> Model | `used_model` | cyan | `sessions.model` column |
| Session -> Session | `delegated` | purple | `sessions.parent_session_id` FK |
| Skill -> Skill | `relates_to` | gold | `metadata.hermes.related_skills` from SKILL.md YAML |

Edges referencing non-existent nodes are filtered out before the response is returned.

### Hit-Testing

- **Quadtree**: `d3.quadtree` provides O(log n) mouse-to-node lookups instead of SVG DOM events
- Quadtree is rebuilt on every simulation tick to stay in sync with node positions
- **Adjacency index**: Pre-built `Map<nodeId, Set<nodeId>>` enables O(degree) neighbor lookups for hover/selection highlighting

### On-Demand Edges

Edges are hidden by default to eliminate the visual "hairball" effect on dense graphs. They appear only when:

- **Hovering** a node: that node's direct connections are drawn
- **Selecting** a node (click): connections remain visible while the node is selected

### Two-Tier Highlight Dimming

Non-relevant nodes are dimmed with two levels of alpha to distinguish hover (exploratory) from selection (committed):

- **Hover**: Non-neighbor nodes dim to alpha 0.4 (subtle, preserves context)
- **Selection (click)**: Non-neighbor nodes dim to alpha 0.15 (stronger, focuses attention)
- Labels follow the same two-tier pattern
- `connectedIds` are filtered against `visibleNodeIds` so hidden node types don't affect neighbor highlighting

### Event Listener Cleanup

Canvas mouse event listeners (mousemove, mousedown, mouseup, click) are registered with an `AbortController` signal. At the start of each `loadGraph()` call, the previous controller is aborted and a new one created. This prevents listener accumulation when changing time scopes or reloading the graph, which previously caused duplicate handlers with stale closures fighting over the canvas.

### Node Position Initialization

Nodes are pre-initialized to positions around the canvas center (using a spiral/phyllotaxis offset) before the simulation starts. This prevents the "phantom cluster" effect where D3's default initialization placed nodes near `(0,0)` while forces centered at `(width/2, height/2)`, causing a visible migration animation on load.

### Node Sizing

Nodes scale with `d3.scaleSqrt()` based on connection count (degree):

- Hub nodes (many connections) render larger
- Leaf nodes (few connections) render smaller
- Radius range: 4px to 22px

### Frontend Interactions

| Action | Behavior |
|--------|----------|
| **Hover** node | Tooltip with name, type, key properties. That node's edges appear. Connected nodes highlighted, others dimmed |
| **Click** node | Right sidebar opens with full metadata and connected neighbors list. Node's edges stay visible |
| **Double-click** any node | Opens draggable floating panel with type-specific detail (see below) |
| **Drag** node | Moves the node within the force simulation |
| **Scroll** | Zoom in/out (scale 0.15x to 5x) |
| **Pan** | Click and drag background |
| **Click** neighbor in sidebar/panel | Opens that node's floating panel + pans graph to it |

### Floating Panels (Double-Click)

All node types support floating detail panels with cross-reference navigation:

| Node Type | Panel Content |
|-----------|---------------|
| **File** | Content preview with copy button for file path |
| **Session** | Structured message history with collapsible tool calls, JSON-highlighted arguments/results, role-colored messages. Copy button for session ID |
| **Tool** | Usage count, clickable session list (opens session panels). Copy button for tool name |
| **Model** | Aggregated token stats (input/output), cost, clickable session list |
| **Skill** | Description, category, enabled status, clickable related skills + sessions |

#### Session Panel Message Rendering

Session floating panels render messages with proper structure:

- **User messages**: escaped content with markdown-like formatting
- **Assistant messages**: text content + collapsible `<details>` blocks for each tool call showing function name and JSON-highlighted arguments
- **Tool results**: collapsible blocks with parsed/highlighted JSON output, matched to the originating tool call by `tool_call_id`. Long results (>2000 chars) are truncated with a "Show more" expand button

#### Cross-Reference Navigation

Clicking any session, tool, file, model, or skill reference inside a floating panel:
1. Opens the appropriate floating panel for that node
2. Pans and zooms the graph canvas to center on the referenced node
3. Selects the node (highlights it and shows its edges)

This replaces the old `onNeighborClick()` behavior which only updated the sidebar.

#### Copy Buttons

Floating panel headers include a `⧉` copy button (visible on hover) that copies the panel's primary identifier (session ID, file path, tool name) to the clipboard. Sidebar metadata rows for session IDs and file paths also have copy buttons.

### Toolbar Controls

| Control | Function |
|---------|----------|
| **Search** (`/` to focus) | Filters nodes by label (dims non-matching) |
| **Node type toggles** | 5 color-coded buttons with live counts: Sessions, Files, Tools, Models, Skills. Client-side filtering (no API reload). Keyboard shortcuts: `1`-`5` |
| **Preset views** | Quick-access buttons: **All**, **S+M** (Sessions+Models), **Tools**, **Skills**. Each presets the type toggles |
| **Degree threshold slider** | "Min connections" slider hides nodes with fewer than N connections |
| **Time scope** dropdown | Filters by time: Last 30 Minutes, Last 1 Hour, Last 3 Hours, Last 6 Hours, Last 12 Hours, Last 24 Hours (default), Last 7 Days, Last 30 Days, All Time |
| **Reset Zoom** | Returns to default zoom level |
| **Badge** | Shows current node and edge counts |
| **Legend** | Bottom-left reference for node type colors |

### Level-of-Detail Labels

Node labels auto-hide when zoom level < 0.6 and auto-show when zooming back in. This keeps the canvas readable at overview zoom levels while providing detail when zoomed in.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1`-`5` | Toggle node types (Sessions, Files, Tools, Models, Skills) |
| `/` | Focus search input |
| `Escape` | Close topmost floating panel (by z-index), or close sidebar if no panels open |
| `f` | Fit graph to viewport (zoom to show all visible nodes) |
| `Enter` | Open floating panel for currently selected node |

### Code Organization in `index.html`

The graph code uses anchor comments for maintainability:

| Anchor | Content |
|--------|---------|
| `/* GRAPH_STYLES_START */` ... `/* GRAPH_STYLES_END */` | All graph CSS (container, toolbar, sidebar, floating panels, legend, tooltip) |
| `<!-- GRAPH_PANEL_START -->` ... `<!-- GRAPH_PANEL_END -->` | Graph panel HTML (toolbar, canvas, tooltip, legend, sidebar) |
| `// GRAPH_RUNTIME_START` ... `// GRAPH_SIDEBAR_END` | Graph JS globals, shape generators, helpers, floating panels, sidebar metadata builder |
| `// GRAPH_INTEGRATION_START` ... `// GRAPH_INTEGRATION_END` | Tab activation, resize handler, toggle listeners |

### Global JS Variables (owned by graph code)

| Variable | Type | Purpose |
|----------|------|---------|
| `graphSim` | D3 simulation | Current force simulation instance |
| `graphData` | object | Raw API response (`{ nodes, edges, node_count, edge_count }`) |
| `graphLoaded` | boolean | Whether graph has loaded at least once (prevents re-fetch on tab revisit) |
| `graphCanvasAbort` | AbortController | Used to abort and re-register canvas event listeners on each `loadGraph()` call, preventing listener accumulation |
| `floatingPanels` | Map | Tracks open floating panels (key -> DOM element) |
| `floatingZCounter` | number | Z-index counter for floating panel stacking |
| `adjacencyIndex` | Map | Pre-built `Map<nodeId, Set<nodeId>>` for O(degree) neighbor lookups |
| `quadtree` | d3.quadtree | Spatial index for O(log n) mouse-to-node hit-testing |

### Exposed Window Functions

These functions are set on `window` inside `loadGraph()` to bridge the closure scope with external event handlers:

| Function | Purpose |
|----------|---------|
| `window._graphApplyFilter(activeTypes)` | Apply node type visibility filter |
| `window._graphApplyDegree(minDegree)` | Apply minimum connection count filter |
| `window._graphPanToNode(nodeId)` | Pan/zoom canvas to center on a node, select it |
| `window._graphFitToViewport()` | Zoom to fit all visible nodes in the viewport |
| `window._graphOpenSelectedPanel()` | Open the floating panel for the currently selected node |

### Frontend Utility Functions

| Function | Purpose |
|----------|---------|
| `highlightJSON(str)` | CSS-only JSON syntax highlighting (wraps keys/strings/numbers/booleans in colored `<span>` elements) |
| `copyToClipboard(text)` | Copies text to clipboard and shows a toast notification |
| `onNeighborClick(nodeId)` | Opens the appropriate floating panel for a node + pans graph to it. Called from inline onclick handlers in panels |

### Backend Helpers in `app.py`

| Function | Purpose |
|----------|---------|
| `_infer_file_category(path)` | Maps file extension to category (python, javascript, config, docs, etc.) |
| `_parse_skill_frontmatter(content)` | Extracts YAML frontmatter from SKILL.md files |
| `get_graph_data(request)` | Main endpoint handler, assembles graph from DB + filesystem |

### Performance Notes

- **Canvas rendering**: Single `<canvas>` element replaces ~9000 SVG DOM elements. All drawing batched in `requestAnimationFrame`
- **Quadtree hit-testing**: `d3.quadtree` for O(log n) mouse lookups, rebuilt every simulation tick
- **Adjacency index**: Pre-built `Map` for O(degree) neighbor lookups, avoids scanning all edges on hover/select
- **On-demand edges**: Only the hovered/selected node's edges are drawn, avoiding full edge rendering
- **Simulation tuning**: `alphaDecay: 0.04`, `velocityDecay: 0.5`, `theta: 1.2`, `distanceMax: 200` (large graphs). Per-type charge strengths and link distances. Centering forces at `0.06-0.08` strength. Drag only reheats simulation on actual movement (not on click), and mouseup cools immediately via `alpha(0.01)`
- Default 24-hour scope keeps the graph manageable (~300-400 nodes)
- All-time view can produce 900+ nodes and 8000+ edges
- `depth=shallow` is a fast fallback (~470 nodes, sessions + models only)
- The `hours` filter is applied at the SQL level for efficiency

## Dashboard UI/UX Features

### Theming (Dark/Light Mode)

- Toggle button in header (sun/moon icon) switches between dark and light themes
- Theme persisted to `localStorage` key `hermes-theme`
- System preference detection via `prefers-color-scheme` media query (used when no localStorage override)
- CSS custom properties system: all colors defined in `:root` (dark) and `[data-theme="light"]` selectors
- Additional utility variables: `--overlay-bg`, `--input-bg`, `--border-subtle`, `--hover-bg`, `--active-bg`
- highlight.js theme auto-swaps between `github-dark` and `github` stylesheets

### Navigation

- **Hash-based routing**: URLs like `#chat`, `#sessions`, `#sessions/detail/{id}`, etc.
- Browser back/forward navigation supported via `hashchange` listener
- `navigateTo(hash)` function for programmatic navigation
- `switchToPanel(panel)` centralizes tab switching, lazy loading, and mobile menu closing
- **Breadcrumbs**: Shown below tabs when viewing sub-routes (e.g., `Sessions > Session abc123`)
- **Mobile hamburger menu**: On screens <= 768px, tabs collapse into a full-screen overlay menu. Hamburger button in header

### Performance

- **Lazy tab loading**: Only chat essentials (`loadStatus`, `loadModels`, `loadPersonalities`) load on init. Other tabs load data on first visit
- **API response caching**: `cachedFetch(url, ttlMs)` with configurable TTL. Sessions: 10s, Memory/Skills: 60s, Secrets: 30s
- **Cache invalidation**: `invalidateCache(url)` called after mutations (toggle skill, save memory, delete session, add/edit/delete secret)
- Tab load tracking via `tabLoaded` object

### Sessions

- **Sort**: Newest First / Oldest First dropdown (uses `sort` query param)
- **Source filter**: Populated from `GET /api/sessions/sources`, filters by session source
- **Pagination**: Prev/Next buttons with page indicator, 50 sessions per page (uses `offset` query param)
- **Stats**: Total session count displayed in toolbar
- **Export**: Per-session JSON export button (downloads full session data as `session-{id}.json`)
- **XSS safety**: Session titles and previews rendered through `escapeHtml()`

### Skills

- **Search**: Free-text search across skill name, description, and ID
- **Category filter**: Dropdown auto-populated from skill IDs (splits on first path segment)
- **Stats**: Shows `N of M skills` in toolbar
- **View content modal**: Click any skill card to view full SKILL.md content + file listing via `/api/skills/{id}/content`
- All skills stored in `allSkills` / `allSkillsDisabled` arrays for client-side filtering

### Memory

- **Character count**: Live char count for both Agent Memory and User Profile textareas
- **Auto-save**: Debounced auto-save (5s delay) with status indicator ("Auto-saving..." / "Auto-saved")
- **Markdown preview**: Toggle button renders memory content using `formatMessageContent()`
- `saveMemory(silent)` accepts silent flag to suppress toast during auto-save

### File Preview

- **Syntax highlighting**: highlight.js 11.9.0 CDN with 40+ language mappings from file extensions
- **Line numbers**: Non-selectable line number gutter alongside code content
- **Theme-aware**: highlight.js stylesheet swaps with dashboard theme (github-dark / github)

### Chat Streaming Performance (Phase 2)

- **Render batching**: SSE content tokens no longer trigger immediate DOM re-renders. A `setInterval` loop at ~30fps checks a `renderDirty` flag and batches all pending content into a single `innerHTML` update per frame
- **Throttled localStorage writes**: `persistActiveAssistantState()` is throttled to once per second during streaming instead of every token. A `persistDirty` flag ensures a final write when the stream ends
- **Render loop lifecycle**: Loop starts when SSE stream connects, stops when stream ends or errors out. Cleanup includes clearing all tool timers

### Tool Call Enrichment (Phase 2)

- **Tool icons**: `getToolIcon()` returns emoji icons based on tool name (e.g., file ops get folder icon, web tools get globe, delegation gets chain link)
- **Header details**: `getToolHeaderDetail()` extracts a human-readable summary from tool arguments (e.g., file path for `read_file`, URL for `web_search`, task description for `delegate_task`)
- **Result summaries**: `getToolResultSummary()` provides a compact one-line summary of tool output (e.g., line count for file reads, success/failure for writes)
- **Delegation progress**: `getDelegationProgressSummary()` formats subagent progress events into readable status updates
- **Nested subagent stream**: expanded `delegate_task` tool blocks render child tool calls, child tool outputs, and child progress events live inside the delegate request body
- **Delegate state preservation**: expanded tool blocks keep their open/closed state across streaming rerenders via stable `data-tool-key` markers
- **In-flight child tools**: running nested tools hide the output section until real output exists, so the UI does not spam `Waiting for tool output...` placeholders while work is still active
- **Structured request/output rendering**: tool payloads are rendered recursively so arrays, nested objects, and multiline values remain readable instead of being reduced to short clipped summaries
- **Live output area**: running tools now surface live progress text in the output area until real output is attached
- **Formatted output**: `formatToolOutputText()` syntax-highlights full JSON/text output without the earlier 3000-character truncation path

### Tool Call Timers (Phase 2)

- **In-flight timing**: `startToolTimer(callId)` records start time when a `tool_call` SSE event arrives. `stopToolTimer(callId)` computes elapsed time when `tool_output` arrives
- **Live timer display**: `startToolTimerUpdates()` / `stopToolTimerUpdates()` run a 1-second interval that updates timer badges on in-flight tool blocks
- **Completion time display**: After a tool completes, its elapsed time (e.g., "2.3s") is shown in the tool block header via `toolCallCompletionTimes` map
- **Timer state**: `toolCallTimers` (Map: callId -> start timestamp) and `toolCallCompletionTimes` (Map: callId -> elapsed string) track active and completed timers

### Debug Log Coverage (Phase 2)

The `log(type, message, isError, details, imageData)` function writes entries to the Debug Log panel. Phase 2 expanded coverage to eliminate silent failures and improve observability:

- **Silent error paths**: All `catch` blocks that previously swallowed errors silently (`console.warn` only or empty catch) now also call `log()`:
  - `saveConversation()`, `loadConversation()`, `saveActiveRun()`, `loadActiveRun()` — localStorage failures
  - SSE JSON parse errors — previously completely silent empty `catch {}`
  - `exportSession()`, `loadSessionSources()`, `viewSkillContent()`, `autoSaveMemory()` — operation failures
- **SSE streaming events**: New log entries for:
  - `run_state` events (session ID assignment — only logged when session ID actually changes)
  - `meta` events (token usage summaries)
  - Delegation-specific tool calls (`delegate_task` logged distinctly from regular tools)
  - Stream lifecycle (render loop start/stop)
  - SSE parse failures with the raw data that failed to parse
- **Navigation/routing**: `navigateTo()` and lazy panel loading now log panel transitions
- **Cache operations**: `cachedFetch()` logs cache hits/misses, `invalidateCache()` logs what was invalidated
- **Tool timers**: `startToolTimer()` / `stopToolTimer()` log call IDs and elapsed times

## Known Operational Gotchas

1. Stale long-running processes caused many earlier "it didn't change" reports.
   Restart the correct process, then hard refresh the browser.

2. If `Chat Context` says `Waiting for token and context stats...`, verify the final `meta` SSE event is arriving.
   The backend and proxy may be correct while the browser still serves stale JS.

3. If chat shows `Hermes gateway is unavailable (All connection attempts failed)`, check whether the API-only server is listening on `127.0.0.1:8642`.

4. If dashboard restarts fail with `address already in use`, an old `uvicorn app:app --port 8081` process is still running.

5. If long-running delegated work appears to stop around 5 minutes, verify both patched processes are running. The fix depends on:
   1. `dashboard/app.py` using an unlimited upstream read timeout
   2. `gateway/platforms/api_server.py` emitting heartbeat chunks during long idle spans

6. If subagent work does not appear inside the expanded delegate block, hard refresh the browser so the updated `index.html` is loaded.

   Also verify both of these are true:
   1. `gateway/platforms/api_server.py` is running from the patched process on `127.0.0.1:8642`
   2. the dashboard web app on `0.0.0.0:8081` was restarted after the latest `templates/index.html` changes

   If the delegate child rows stay on `No output yet.` after the tool completes, the browser is likely still serving stale JS that predates the synthetic-child/output merge fix.

7. If the full gateway is used instead of the API-only server, Telegram/Discord env vars may interfere with restart reliability.

8. `api_server` does not auto-load default MCP servers in this setup. If you explicitly add an MCP server like `becomussy` back under `platform_toolsets.api_server`, expect prompt size to increase significantly.

## Useful Checks

```sh
curl -s http://127.0.0.1:8081/
curl -s http://127.0.0.1:8081/api/models
curl -s http://127.0.0.1:8081/api/graph?depth=full&hours=24
curl -s http://127.0.0.1:8642/health
ss -ltnp | grep 8081
ss -ltnp | grep 8642
pgrep -af "run_api_server_only.py"
pgrep -af "uvicorn app:app --host 0.0.0.0 --port 8081"
```

## Logs

- Dashboard log: `/tmp/hermes-dashboard.log`
- API-only server log: `/tmp/hermes-api-only.log`

When doing troubleshooting, prefer checking the raw stream from `/chat` and from `/v1/chat/completions` before changing frontend code again.
