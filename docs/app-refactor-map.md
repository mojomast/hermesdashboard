# app.py Backend Refactor Map
## Task frame
Bounded-context audit for surgical extraction of the Hermes Dashboard backend monolith. Scope is `/home/mojo/.hermes/repos/hermesdashboard-refactor-20260601/app.py`; `/home/mojo/.hermes/dashboard` is read-only parity reference. Keep `app.py` as route/bootstrap orchestrator until leaf service extractions are test-gated and committed.
## Summary
- Total lines: 9858
- Rough top-level function count: 346 (1 top-level classes)
- Route declarations: 99
- Route groups: `agent-observability`=1, `autonomous-development`=4, `campaigns`=2, `chat`=1, `config`=2, `cron`=8, `dashboard`=1, `dashboard-state`=3, `diagnostics`=1, `dnd`=17, `doom`=2, `files`=1, `games`=2, `graph`=1, `health`=1, `memory`=2, `message-board`=3, `minihack`=2, `model`=1, `models`=1, `personalities`=1, `personality`=1, `pokemon`=7, `root`=1, `runs`=1, `scrolls`=8, `secrets`=3, `self-improvement`=6, `sessions`=9, `settings`=1, `skills`=3, `status`=1, `token-usage`=1
- Top-level mutable/global state list (audit heuristic):
  - `HERMES_AGENT_PATH` (line 75)
  - `HERMES_API` (line 274)
  - `HERMES_HOME` (line 275)
  - `DASHBOARD_REPO_ROOT` (line 276)
  - `SELF_IMPROVEMENT_HOME` (line 279)
  - `API_KEY` (line 282)
  - `DASHBOARD_PORT` (line 285)
  - `HERMES_READ_TIMEOUT_RAW` (line 286)
  - `HERMES_READ_TIMEOUT` (line 287)
  - `HERMES_USEFUL_EVENT_TIMEOUT` (line 292)
  - `ACTIVE_RUN_TTL_SECONDS` (line 301)
  - `ACTIVE_RUNS` (line 302)
  - `ACTIVE_CHILD_STREAMS` (line 303)
  - `ACTIVE_SESSION_STEER_MESSAGES` (line 304)
  - `_STARTUP_METADATA_BACKFILL_STARTED` (line 305)
  - `DASHBOARD_STATE_DB_PATH` (line 306)
  - `DASHBOARD_STATE_KEYS` (line 307)
  - `DASHBOARD_STATE_LOCK` (line 308)
  - `INTERRUPT_FLAGS` (line 313)
  - `BUILT_IN_PERSONALITIES` (line 323)
  - `EXTRA_SECRET_METADATA` (line 340)
  - `WEB_BACKENDS` (line 385)
  - `TTS_PROVIDERS` (line 386)
  - `STT_PROVIDERS` (line 387)
  - `BUSY_INPUT_MODES` (line 388)
  - `TOOL_PROGRESS_MODES` (line 389)
  - `BACKGROUND_NOTIFICATION_MODES` (line 390)
  - `RESUME_DISPLAY_MODES` (line 391)
  - `APPROVAL_MODES` (line 392)
  - `REASONING_EFFORTS` (line 393)
  - `MODEL_COST_TABLE` (line 396)
  - `TOKEN_USAGE_FIELDS` (line 2295)
  - `SKILL_DESCRIPTIONS` (line 3152)
  - `SKILL_DESCRIPTIONS` (line 3200)
  - `DOOM_WATCH_SERVER_URL` (line 3457)
  - `MINIHACK_WATCH_SERVER_URL` (line 3458)
  - `POKEMON_SERVER_URL` (line 3459)
  - `POKEMON_AGENT_ROOT` (line 3460)
  - `POKEMON_ROM_PATH` (line 3461)
  - `POKEMON_DATA_DIR` (line 3462)
  - `POKEMON_LOG_DIR` (line 3463)
  - `SELF_IMPROVEMENT_ALLOWED_LAYERS` (line 3999)
  - `SELF_IMPROVEMENT_BANNED_PHRASES` (line 4009)
  - `AUTONOMOUS_DEVELOPMENT_DEFAULT_PIPELINES` (line 5215)
  - `DND_CONTROLLER_TYPES` (line 7157)
  - `DND_CHARACTER_KINDS` (line 7158)
  - `DND_WORLD_ENTITY_TYPES` (line 7159)
  - `DND_SCHEMA_REGISTRY` (line 7160)
  - `DND_TURN_LOCKS` (line 7171)
  - `DND_AUTO_TURN_JOBS` (line 7172)
  - `DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN` (line 7173)
  - `DND_AUTO_TURN_JOB_TTL_SECONDS` (line 7174)
  - `_SCROLLS_PROJECT_ROOT` (line 8624)
  - `_SCROLLS_LOOP_LOCK` (line 8628)
  - `_SCROLLS_LOOP_STOP` (line 8629)
  - `_SCROLLS_LOOP_STATE` (line 8630)
  - `routes` (line 9720)
  - `app` (line 9853)

## Vocabulary map
- **API route:** Starlette HTTP/WebSocket route declaration that maps an external path and method to an endpoint wrapper. Routes preserve public paths and should delegate to services.
- **session:** A persisted or streamed dashboard conversation/execution unit; not the same as a browser tab or subprocess job.
- **active run:** In-memory live chat/run execution state keyed by session/run identifiers, including interrupt/steer/stop coordination.
- **child stream:** Subagent or child process event stream attached to an active run; child events are routed to projections consumed by the frontend.
- **dashboard state:** SQLite-backed browser/dashboard projection state (conversation and active-run state) owned by `dashboard_backend/services/dashboard_state.py`.
- **message board post/message:** Durable message-board database record rendered by the board API; distinct from chat messages and IRC/dashboard-chat messages.
- **cron job:** Scheduled job definition or live trigger managed through Hermes cron APIs/files; mutating it has filesystem/scheduler side effects.
- **self-improvement candidate/run/event:** Candidate = proposed self-improvement work item; run = execution cycle directory/projection; event = ledger row used to derive coverage/readiness/anomaly projections.
- **autonomous pipeline:** Registry entry grouping autonomous-development specs and linked cron jobs; controls can create/edit registry records and enable/disable jobs.
- **graph node/edge:** Graph projection objects surfaced through graph APIs, distinct from memory records and execution traces.

## Bounded context map
| Proposed module path | Owned functions/classes/constants | State dependencies | Routes exposed | Tests covering it |
|---|---|---|---|---|
| dashboard_backend/core/paths.py | repo/user/home path constants, safe path helpers | HOME_DIR/HERMES paths, env vars | used by most routes | shared import tests + full pytest |
| dashboard_backend/core/responses.py | JSON/HTML/plain response helpers and error envelopes | none or Starlette response classes | all API wrappers | full pytest |
| dashboard_backend/core/config.py | settings, models, personality, secrets, provider config | CONFIG caches/env | /api/settings, /api/models, /api/personality, /api/secrets | settings/model tests |
| dashboard_backend/services/token_usage.py | ✅ EXTRACTED: TOKEN_USAGE_FIELDS and token usage aggregation helpers; app wrappers remain | session DB/filesystem reads only | /api/token-usage via wrapper/route | tests/test_token_usage_dashboard.py |
| dashboard_backend/services/message_board.py | ✅ EXTRACTED: message-board SQLite schema/read/write helpers; endpoint wrappers remain in app.py | message board sqlite path via HERMES_HOME | /api/message-board* via app wrappers | tests/test_message_board.py |
| dashboard_backend/services/sessions.py | session listing, traces, transcript/history projections | session paths/caches | /api/sessions*, /api/traces* | session/execution trace tests |
| dashboard_backend/services/dashboard_state.py | SQLite persistence for browser dashboard state | state sqlite path | /api/dashboard-state/* | tests/test_dashboard_state_persistence.py |
| dashboard_backend/services/active_runs.py + child_streams.py | live chat stream orchestration, active run state, child event routing | ACTIVE_RUNS, ACTIVE_CHILD_STREAMS, STEER_MESSAGES, INTERRUPT_FLAGS | /chat, /api/session/* stream/control | high-risk streaming tests + full pytest |
| dashboard_backend/services/self_improvement.py | self-improvement status, candidates, event coverage, controls | SELF_IMPROVEMENT_HOME, cron jobs, outbox files | /api/self-improvement* | tests/test_self_improvement_panel.py |
| dashboard_backend/services/autonomous_development.py | pipeline registry/projections/control | ~/.hermes/autonomous-development, cron jobs | /api/autonomous-development* | tests/test_autonomous_development_panel.py |
| dashboard_backend/services/cron.py | cron list/create/update/delete/run/pause/resume proxy | Hermes API, cron files | /api/cron* | cron tests/full pytest |
| dashboard_backend/services/graph.py | graph node/edge/search projections | memory/skills/session stores | /api/graph* | graph/execution tests |
| dashboard_backend/services/dnd.py | campaign/narrative state APIs | campaign JSON/files | /api/dnd* | DND tests if present/full pytest |
| dashboard_backend/services/games_catalog.py | ✅ PARTIAL: read-only Games tab skill catalog/frontmatter projection; Pokemon/MiniHack/Doom proxy/process helpers remain in app.py | `HERMES_HOME` injected at call time | /api/games via app wrapper | tests/test_games_catalog_service.py, tests/test_games_tab.py |
| dashboard_backend/services/scrolls.py | ✅ PARTIAL: read-only `/api/scrolls/snapshot` state projection delegation; broader Scrolls status/artifact/loop helpers remain in app.py | scrolls project root injected at call time | /api/scrolls/snapshot via app wrapper; other /api/scrolls* via app.py | tests/test_scrolls_snapshot.py, tests/test_scrolls_panel_navigation.py |
| dashboard_backend/routes/*.py | route wrappers that parse Request and call services | imports services only | same public paths | route presence tests |

## Function registry
| Name | Line Range | Responsibility | Target Module | Shared State Dependencies |
|---|---:|---|---|---|
| `_hermes_agent_path` | 68-72 | `def _hermes_agent_path() -> Path:     configured = os.getenv("HERMES_AGENT_PATH")     if configured:         return Path` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `set_interrupt_flag` | 316-317 | `def set_interrupt_flag(session_id: str, value: bool) -> None:     INTERRUPT_FLAGS[session_id] = value` | `dashboard_backend/services/active_runs.py + child_streams.py` | INTERRUPT_FLAGS |
| `check_interrupt_flag` | 320-321 | `def check_interrupt_flag(session_id: str) -> bool:     return INTERRUPT_FLAGS.get(session_id, False)` | `dashboard_backend/services/active_runs.py + child_streams.py` | INTERRUPT_FLAGS |
| `_cleanup_active_runs` | 401-422 | `def _cleanup_active_runs() -> None:     now = time.time()     expired = []     for run_id, state in ACTIVE_RUNS.items():` | `dashboard_backend/services/active_runs.py + child_streams.py` | ACTIVE_CHILD_STREAMS, ACTIVE_RUNS, ACTIVE_RUN_TTL_SECONDS |
| `_event_metadata` | 425-447 | `def _event_metadata(payload: dict) -> dict:     metadata = {}     args = payload.get("arguments")     if isinstance(args` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_register_child_stream` | 450-472 | `def _register_child_stream(run_id: str, payload: dict) -> None:     metadata = _event_metadata(payload)     child_sessio` | `dashboard_backend/services/active_runs.py + child_streams.py` | ACTIVE_CHILD_STREAMS |
| `_route_child_stream_event` | 475-504 | `def _route_child_stream_event(run_id: str, payload: dict) -> None:     payload_type = payload.get("type")     if payload` | `dashboard_backend/services/active_runs.py + child_streams.py` | ACTIVE_CHILD_STREAMS |
| `_normalize_sse_payload` | 507-541 | `def _normalize_sse_payload(parsed: dict) -> list[dict]:     payloads: list[dict] = []     if parsed.get("tool") and not ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_sanitize_chat_messages` | 544-568 | `def _sanitize_chat_messages(messages: list) -> list:     sanitized = []     for msg in messages or []:         if not is` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_log_stream` | 571-572 | `def _log_stream(run_id: str, message: str) -> None:     print(f"[dashboard:/chat:{run_id}] {message}", file=sys.stderr, ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_dashboard_state_connect` | 575-576 | `def _dashboard_state_connect() -> sqlite3.Connection:     return _dashboard_state_connect_impl(DASHBOARD_STATE_DB_PATH)` | `dashboard_backend/services/dashboard_state.py` | DASHBOARD_STATE_DB_PATH |
| `_validate_dashboard_state_key` | 579-580 | `def _validate_dashboard_state_key(key: str) -> str:     return _validate_dashboard_state_key_impl(key, DASHBOARD_STATE_K` | `dashboard_backend/services/dashboard_state.py` | DASHBOARD_STATE_KEYS |
| `_load_dashboard_state` | 583-589 | `def _load_dashboard_state(key: str):     return _load_dashboard_state_impl(         key,         db_path=DASHBOARD_STATE` | `dashboard_backend/services/dashboard_state.py` | DASHBOARD_STATE_DB_PATH, DASHBOARD_STATE_KEYS, DASHBOARD_STATE_LOCK |
| `_save_dashboard_state` | 592-599 | `def _save_dashboard_state(key: str, value) -> None:     _save_dashboard_state_impl(         key,         value,         ` | `dashboard_backend/services/dashboard_state.py` | DASHBOARD_STATE_DB_PATH, DASHBOARD_STATE_KEYS, DASHBOARD_STATE_LOCK |
| `_delete_dashboard_state` | 602-608 | `def _delete_dashboard_state(key: str) -> None:     _delete_dashboard_state_impl(         key,         db_path=DASHBOARD_` | `dashboard_backend/services/dashboard_state.py` | DASHBOARD_STATE_DB_PATH, DASHBOARD_STATE_KEYS, DASHBOARD_STATE_LOCK |
| `get_dashboard_state` | 611-617 | `async def get_dashboard_state(request):     key = request.path_params["key"]     try:         found, value = _load_dashb` | `dashboard_backend/services/dashboard_state.py` | — |
| `set_dashboard_state` | 620-632 | `async def set_dashboard_state(request):     key = request.path_params["key"]     try:         data = json.loads(await re` | `dashboard_backend/services/dashboard_state.py` | — |
| `delete_dashboard_state` | 635-641 | `async def delete_dashboard_state(request):     key = request.path_params["key"]     try:         _delete_dashboard_state` | `dashboard_backend/services/dashboard_state.py` | — |
| `_run_chat_stream_sync` | 644-757 | `def _run_chat_stream_sync(run_id: str, messages: list, session_id: Optional[str]) -> None:     state = ACTIVE_RUNS[run_i` | `dashboard_backend/services/active_runs.py + child_streams.py` | ACTIVE_RUNS, API_KEY, HERMES_API, HERMES_READ_TIMEOUT, HERMES_USEFUL_EVENT_TIMEOUT |
| `_run_chat_stream` | 760-889 | `async def _run_chat_stream(     run_id: str, messages: list, session_id: Optional[str] ) -> None:     await asyncio.to_t` | `dashboard_backend/services/active_runs.py + child_streams.py` | ACTIVE_RUNS, API_KEY, HERMES_API, HERMES_READ_TIMEOUT, HERMES_USEFUL_EVENT_TIMEOUT |
| `_child_session_ids` | 892-897 | `def _child_session_ids(conn: sqlite3.Connection, session_id: str) -> list[str]:     cursor = conn.execute(         "SELE` | `dashboard_backend/services/sessions.py` | — |
| `_related_session_artifacts` | 900-947 | `def _related_session_artifacts(session_ids: list[str]) -> list[dict]:     sessions_dir = HERMES_HOME / "sessions"     if` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `_session_activity_payload` | 950-1091 | `def _session_activity_payload(conn: sqlite3.Connection, session_id: str) -> dict:     session_ids = [session_id] + _chil` | `dashboard_backend/services/sessions.py` | — |
| `_session_overview_payload` | 1094-1107 | `def _session_overview_payload(conn: sqlite3.Connection, session_id: str) -> dict:     child_rows = conn.execute(        ` | `dashboard_backend/services/sessions.py` | — |
| `_sessions_table_exists` | 1110-1114 | `def _sessions_table_exists(conn: sqlite3.Connection) -> bool:     cursor = conn.execute(         "SELECT name FROM sqlit` | `dashboard_backend/services/sessions.py` | — |
| `_sessions_table_has_column` | 1117-1126 | `def _sessions_table_has_column(conn: sqlite3.Connection, column_name: str) -> bool:     try:         rows = conn.execute` | `dashboard_backend/services/sessions.py` | — |
| `_ensure_sessions_summary_column` | 1129-1135 | `def _ensure_sessions_summary_column(conn: sqlite3.Connection) -> None:     if not _sessions_table_exists(conn):         ` | `dashboard_backend/services/sessions.py` | — |
| `_sqlite_table_exists` | 1138-1143 | `def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:     cursor = conn.execute(         "SELECT ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_sqlite_table_columns` | 1146-1154 | `def _sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:     try:         rows = conn.execute(f` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_parse_dashboard_timestamp` | 1157-1185 | `def _parse_dashboard_timestamp(value: object) -> Optional[datetime.datetime]:     if not value:         return None     ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_tool_output_failed` | 1188-1202 | `def _tool_output_failed(content: object) -> bool:     payload = _safe_json_loads(content) if isinstance(content, str) el` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_empty_agent_observability_report` | 1205-1233 | `def _empty_agent_observability_report(window_hours: int, reason: str) -> dict:     return {         "window_hours": wind` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `get_agent_observability_report` | 1236-1403 | `def get_agent_observability_report(window_hours: int = 24, trace_limit: int = 8) -> dict:     """Aggregate recent Hermes` | `app.py/bootstrap or dashboard_backend/core/*` | HERMES_HOME |
| `_clean_transcript_seed_text` | 1406-1429 | `def _clean_transcript_seed_text(text: str) -> str:     cleaned = " ".join(str(text or "").split()).strip()     if not cl` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_extract_tool_output_preview` | 1432-1441 | `def _extract_tool_output_preview(raw_content: str) -> str:     payload = _safe_json_loads(raw_content)     if isinstance` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_extract_summary_from_messages` | 1444-1508 | `def _extract_summary_from_messages(     messages: list[dict], session_meta: Optional[dict] = None ) -> Optional[str]:   ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_extract_title_from_messages` | 1511-1603 | `def _extract_title_from_messages(     messages: list[dict], session_meta: Optional[dict] = None ) -> Optional[str]:     ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_refresh_local_session_metadata` | 1606-1701 | `def _refresh_local_session_metadata(     conn: sqlite3.Connection, session_id: str, force: bool = False ) -> dict[str, O` | `dashboard_backend/services/sessions.py` | — |
| `get_raw_config` | 1704-1709 | `def get_raw_config():     config_path = HERMES_HOME / "config.yaml"     if config_path.exists():         with open(confi` | `dashboard_backend/core/config.py` | HERMES_HOME |
| `get_config` | 1712-1713 | `def get_config():     return load_hermes_config()` | `dashboard_backend/core/config.py` | — |
| `save_config` | 1716-1717 | `def save_config(config):     save_hermes_config(config)` | `dashboard_backend/core/config.py` | — |
| `get_env` | 1720-1721 | `def get_env():     return load_hermes_env()` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `save_env` | 1724-1728 | `def save_env(env):     env_path = HERMES_HOME / ".env"     with open(env_path, "w") as f:         for key, value in env.` | `app.py/bootstrap or dashboard_backend/core/*` | HERMES_HOME |
| `_save_env_value_local` | 1731-1734 | `def _save_env_value_local(key: str, value: str) -> None:     env = get_env()     env[key] = value     save_env(env)` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_mask_secret` | 1737-1740 | `def _mask_secret(value: str) -> str:     if not value or len(value) < 8:         return "****" if value else ""     retu` | `dashboard_backend/core/config.py` | — |
| `_normalize_model_config` | 1743-1749 | `def _normalize_model_config(config: dict) -> dict:     model = config.get("model")     if isinstance(model, str):       ` | `dashboard_backend/core/config.py` | — |
| `_known_secret_catalog` | 1752-1765 | `def _known_secret_catalog() -> dict[str, dict]:     catalog = {**OPTIONAL_ENV_VARS, **EXTRA_SECRET_METADATA}     catalog` | `dashboard_backend/core/config.py` | EXTRA_SECRET_METADATA |
| `_friendly_secret_name` | 1768-1775 | `def _friendly_secret_name(key: str, meta: dict) -> str:     prompt = str(meta.get("prompt") or "").strip()     if prompt` | `dashboard_backend/core/config.py` | — |
| `_build_secrets_payload` | 1778-1822 | `def _build_secrets_payload(env: dict) -> list[dict]:     catalog = _known_secret_catalog()     secrets = []     seen: se` | `dashboard_backend/core/config.py` | — |
| `_count_changed_values` | 1825-1839 | `def _count_changed_values(current, default) -> int:     if isinstance(default, dict):         if not isinstance(current,` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_platform_toolset_extras` | 1842-1855 | `def _platform_toolset_extras(raw_config: dict) -> dict[str, list[str]]:     configurable = {key for key, _, _ in CONFIGU` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_resolved_platform_toolsets` | 1858-1864 | `def _resolved_platform_toolsets(config: dict) -> dict[str, list[str]]:     configurable = {key for key, _, _ in CONFIGUR` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_settings_payload` | 1867-1941 | `def _settings_payload() -> dict:     effective = get_config()     raw = get_raw_config()     env = get_env()     model =` | `dashboard_backend/core/config.py` | APPROVAL_MODES, BACKGROUND_NOTIFICATION_MODES, BUILT_IN_PERSONALITIES, BUSY_INPUT_MODES, REASONING_EFFORTS, RESUME_DISPLAY_MODES, STT_PROVIDERS, TOOL_PROGRESS_MODES, TTS_PROVIDERS, WEB_BACKENDS |
| `homepage` | 1944-1949 | `async def homepage(request):     response = templates.TemplateResponse(request, "index.html")     response.headers["Cach` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `chat_stream` | 1952-2081 | `async def chat_stream(request):     body = await request.body()     data = json.loads(body)     run_id = str(data.get("r` | `dashboard_backend/services/active_runs.py + child_streams.py` | ACTIVE_RUNS |
| `health` | 2084-2085 | `async def health(request):     return JSONResponse({"status": "ok"})` | `dashboard_backend/services/diagnostics.py` | — |
| `get_status` | 2088-2122 | `async def get_status(request):     config = get_config()     env = get_env()     model = _normalize_model_config(config)` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `get_config_endpoint` | 2125-2126 | `async def get_config_endpoint(request):     return JSONResponse(get_raw_config())` | `dashboard_backend/core/config.py` | — |
| `get_settings` | 2129-2130 | `async def get_settings(request):     return JSONResponse(_settings_payload())` | `dashboard_backend/core/config.py` | — |
| `update_config` | 2133-2151 | `async def update_config(request):     body = await request.body()     updates = json.loads(body)     config = get_raw_co` | `dashboard_backend/core/config.py` | — |
| `get_models` | 2154-2226 | `async def get_models(request):     env = get_env()     config = get_config()     model_config = _normalize_model_config(` | `dashboard_backend/core/config.py` | — |
| `get_personalities` | 2229-2242 | `async def get_personalities(request):     config = get_config()     custom = (         list((config.get("agent", {}).get` | `app.py/bootstrap or dashboard_backend/core/*` | BUILT_IN_PERSONALITIES |
| `set_personality` | 2245-2256 | `async def set_personality(request):     body = await request.body()     data = json.loads(body)     personality = data.g` | `dashboard_backend/core/config.py` | — |
| `set_model` | 2259-2280 | `async def set_model(request):     body = await request.body()     data = json.loads(body)     model = data.get("model") ` | `dashboard_backend/core/config.py` | — |
| `get_agent_observability_endpoint` | 2283-2292 | `async def get_agent_observability_endpoint(request):     try:         window_hours = int(request.query_params.get("windo` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_empty_token_usage_window` | 2304-2316 | `def _empty_token_usage_window(label: str, *, start: float | None = None, end: float | None = None, source: str = "api_ca` | `dashboard_backend/services/token_usage.py` | TOKEN_USAGE_FIELDS |
| `_token_usage_total` | 2319-2320 | `def _token_usage_total(row: dict) -> int:     return int(sum(int(row.get(field) or 0) for field in TOKEN_USAGE_FIELDS))` | `dashboard_backend/services/token_usage.py` | TOKEN_USAGE_FIELDS |
| `_window_from_row` | 2323-2333 | `def _window_from_row(label: str, row: sqlite3.Row | dict | None, *, start: float | None = None, end: float | None = None` | `app.py/bootstrap or dashboard_backend/core/*` | TOKEN_USAGE_FIELDS |
| `_aggregate_token_usage_api_calls` | 2336-2360 | `def _aggregate_token_usage_api_calls(conn: sqlite3.Connection, label: str, *, start: float | None = None, end: float | N` | `dashboard_backend/services/token_usage.py` | TOKEN_USAGE_FIELDS |
| `_aggregate_token_usage_sessions` | 2363-2395 | `def _aggregate_token_usage_sessions(conn: sqlite3.Connection, label: str, *, start: float | None = None, end: float | No` | `dashboard_backend/services/token_usage.py` | TOKEN_USAGE_FIELDS |
| `get_token_usage_summary` | 2398-2473 | `def get_token_usage_summary(*, now: datetime.datetime | None = None, current_session_id: str | None = None) -> dict:    ` | `dashboard_backend/services/token_usage.py` | HERMES_HOME |
| `get_token_usage_endpoint` | 2476-2478 | `async def get_token_usage_endpoint(request):     session_id = str(request.query_params.get("session_id") or "").strip() ` | `dashboard_backend/services/token_usage.py` | — |
| `get_sessions` | 2481-2566 | `async def get_sessions(request):     db_path = HERMES_HOME / "state.db"     if not db_path.exists():         return JSON` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `search_sessions` | 2569-2712 | `async def search_sessions(request):     db_path = HERMES_HOME / "state.db"     if not db_path.exists():         return J` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `get_session_sources` | 2715-2728 | `async def get_session_sources(request):     db_path = HERMES_HOME / "state.db"     if not db_path.exists():         retu` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `get_session` | 2731-2821 | `async def get_session(request):     session_id = request.path_params["session_id"]     db_path = HERMES_HOME / "state.db` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `backfill_session_summaries_endpoint` | 2824-2868 | `async def backfill_session_summaries_endpoint(request):     try:         body = await request.body()         data = json` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `regenerate_session_summary_endpoint` | 2871-2897 | `async def regenerate_session_summary_endpoint(request):     session_id = request.path_params["session_id"]     db_path =` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `_run_startup_session_metadata_backfill` | 2900-2934 | `def _run_startup_session_metadata_backfill() -> None:     global _STARTUP_METADATA_BACKFILL_STARTED     if _STARTUP_META` | `dashboard_backend/services/sessions.py` | HERMES_HOME, _STARTUP_METADATA_BACKFILL_STARTED |
| `_lifespan` | 2938-2940 | `async def _lifespan(_app):     _run_startup_session_metadata_backfill()     yield` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_dashboard_allowed_roots` | 2943-2958 | `def _dashboard_allowed_roots() -> list[Path]:     roots: list[Path] = []     env_root = os.getenv("HERMES_WRITE_SAFE_ROO` | `app.py/bootstrap or dashboard_backend/core/*` | HERMES_HOME |
| `_resolve_allowed_path` | 2961-2974 | `def _resolve_allowed_path(raw_path: str) -> Optional[Path]:     if not raw_path:         return None     try:         ca` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_safe_json_loads` | 2977-2983 | `def _safe_json_loads(value: str):     if not value:         return None     try:         return json.loads(value)` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_collect_paths_from_payload` | 2986-3006 | `def _collect_paths_from_payload(payload) -> list[str]:     paths: list[str] = []     if isinstance(payload, dict):      ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `get_session_files` | 3009-3079 | `async def get_session_files(request):     session_id = request.path_params["session_id"]     db_path = HERMES_HOME / "st` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `get_file_content` | 3082-3097 | `async def get_file_content(request):     raw_path = request.query_params.get("path", "")     resolved = _resolve_allowed` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `delete_session` | 3100-3113 | `async def delete_session(request):     session_id = request.path_params["session_id"]     db_path = HERMES_HOME / "state` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `get_memory` | 3116-3131 | `async def get_memory(request):     memory_path = HERMES_HOME / "memories" / "MEMORY.md"     user_path = HERMES_HOME / "m` | `app.py/bootstrap or dashboard_backend/core/*` | HERMES_HOME |
| `update_memory` | 3134-3149 | `async def update_memory(request):     body = await request.body()     data = json.loads(body)      memory_dir = HERMES_H` | `app.py/bootstrap or dashboard_backend/core/*` | HERMES_HOME |
| `parse_description_md` | 3183-3197 | `def parse_description_md(filepath):     """Parse DESCRIPTION.md with YAML frontmatter."""     try:         with open(fil` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_iter_skill_dirs` | 3233-3254 | `def _iter_skill_dirs(skills_dir: Path):     """Yield concrete skill directories from both flat and category/skill layout` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_skill_category` | 3257-3262 | `def _skill_category(skill_dir: Path, skills_root: Path) -> str:     try:         rel = skill_dir.relative_to(skills_root` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_find_skill_dir` | 3265-3272 | `def _find_skill_dir(skill_id: str) -> Optional[Path]:     safe_id = Path(str(skill_id)).name     if not safe_id or safe_` | `app.py/bootstrap or dashboard_backend/core/*` | HERMES_HOME |
| `get_skills` | 3275-3314 | `async def get_skills(request):     skills_dir = HERMES_HOME / "skills"     skills = []      for item in _iter_skill_dirs` | `app.py/bootstrap or dashboard_backend/core/*` | HERMES_HOME, SKILL_DESCRIPTIONS |
| `toggle_skill` | 3317-3339 | `async def toggle_skill(request):     body = await request.body()     data = json.loads(body)     skill_id = data.get("sk` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `get_skill_content` | 3342-3364 | `async def get_skill_content(request):     skill_id = request.path_params["skill_id"]     skills_dir = _find_skill_dir(sk` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_parse_game_skill_frontmatter` | 3367-3382 | `def _parse_game_skill_frontmatter(skill_md: Path) -> dict:     """Return YAML frontmatter from a game SKILL.md file, tol` | `dashboard_backend/services/games.py` | — |
| `_categorize_game_skill` | 3385-3399 | `def _categorize_game_skill(tags: list[str], description: str) -> str:     haystack = " ".join(tags + [description]).lowe` | `dashboard_backend/services/games.py` | — |
| `get_games_catalog` | 3402-3450 | `def get_games_catalog() -> dict:     """Discover gaming-related Hermes skills for the dashboard Games tab."""     gaming` | `dashboard_backend/services/games.py` | HERMES_HOME |
| `get_games_endpoint` | 3453-3454 | `async def get_games_endpoint(request):     return JSONResponse(get_games_catalog())` | `dashboard_backend/services/games.py` | — |
| `_diagnostics_fetch_json` | 3466-3476 | `async def _diagnostics_fetch_json(client, url, timeout=5.0):     try:         response = await client.get(url, timeout=t` | `dashboard_backend/services/diagnostics.py` | — |
| `_diagnostics_redact` | 3479-3493 | `def _diagnostics_redact(value):     if isinstance(value, dict):         redacted = {}         for key, item in value.ite` | `dashboard_backend/services/diagnostics.py` | — |
| `diagnostics_context_endpoint` | 3496-3524 | `async def diagnostics_context_endpoint(request):     target = request.query_params.get("target", "pokemon")     base = P` | `dashboard_backend/services/diagnostics.py` | ACTIVE_RUNS, HERMES_API, POKEMON_SERVER_URL |
| `_pokemon_port` | 3527-3529 | `def _pokemon_port() -> str:     match = re.search(r":(\d+)(?:/|$)", POKEMON_SERVER_URL)     return match.group(1) if mat` | `dashboard_backend/services/games.py` | POKEMON_SERVER_URL |
| `_proc_cmdline` | 3532-3537 | `def _proc_cmdline(pid: int) -> list[str]:     try:         raw = Path(f"/proc/{pid}/cmdline").read_bytes()     except Ex` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_pokemon_process_kind` | 3540-3554 | `def _pokemon_process_kind(cmdline: list[str]) -> str | None:     if not cmdline:         return None     joined = " ".jo` | `dashboard_backend/services/games.py` | POKEMON_AGENT_ROOT |
| `_pokemon_related_processes` | 3557-3570 | `def _pokemon_related_processes() -> list[dict]:     processes = []     for entry in Path("/proc").iterdir():         if ` | `dashboard_backend/services/games.py` | — |
| `_terminate_pokemon_processes` | 3573-3600 | `def _terminate_pokemon_processes(timeout: float = 5.0) -> list[dict]:     targets = _pokemon_related_processes()     for` | `dashboard_backend/services/games.py` | — |
| `_start_pokemon_processes` | 3603-3654 | `def _start_pokemon_processes() -> dict:     python = POKEMON_AGENT_ROOT / ".venv" / "bin" / "python"     pokemon_agent =` | `dashboard_backend/services/games.py` | POKEMON_AGENT_ROOT, POKEMON_DATA_DIR, POKEMON_LOG_DIR, POKEMON_ROM_PATH, POKEMON_SERVER_URL |
| `_restart_pokemon_agent` | 3657-3669 | `def _restart_pokemon_agent() -> dict:     stopped = _terminate_pokemon_processes()     started = _start_pokemon_processe` | `dashboard_backend/services/games.py` | POKEMON_SERVER_URL |
| `restart_pokemon_endpoint` | 3672-3677 | `async def restart_pokemon_endpoint(request):     try:         result = await asyncio.to_thread(_restart_pokemon_agent)  ` | `dashboard_backend/services/games.py` | — |
| `_rewrite_doom_watch_html` | 3680-3697 | `def _rewrite_doom_watch_html(html: str) -> str:     """Make upstream Doom watch HTML safe under the dashboard /doom/ pro` | `dashboard_backend/services/games.py` | — |
| `doom_watch_proxy_endpoint` | 3700-3773 | `async def doom_watch_proxy_endpoint(request):     """Proxy the local ViZDoom watch server through the dashboard origin. ` | `dashboard_backend/services/games.py` | DOOM_WATCH_SERVER_URL |
| `minihack_watch_proxy_endpoint` | 3776-3822 | `async def minihack_watch_proxy_endpoint(request):     """Proxy the local MiniHack watch server through the dashboard ori` | `dashboard_backend/services/games.py` | MINIHACK_WATCH_SERVER_URL |
| `_rewrite_pokemon_dashboard_js` | 3825-3845 | `def _rewrite_pokemon_dashboard_js(js: str) -> str:     """Scope the standalone pokemon-agent dashboard JS under /pokemon` | `dashboard_backend/services/games.py` | — |
| `_pokemon_upstream_path` | 3848-3854 | `def _pokemon_upstream_path(path: str) -> str:     path = (path or "").lstrip("/")     if not path:         return "/dash` | `dashboard_backend/services/games.py` | — |
| `pokemon_websocket_proxy_endpoint` | 3857-3905 | `async def pokemon_websocket_proxy_endpoint(websocket: WebSocket):     path = websocket.path_params.get("path", "")     i` | `dashboard_backend/services/games.py` | POKEMON_SERVER_URL |
| `pokemon_proxy_endpoint` | 3908-3981 | `async def pokemon_proxy_endpoint(request):     """Proxy the local pokemon-agent dashboard/API through Hermes Dashboard. ` | `dashboard_backend/services/games.py` | POKEMON_SERVER_URL |
| `get_game_content_endpoint` | 3984-3996 | `async def get_game_content_endpoint(request):     game_id = request.path_params["game_id"]     safe_id = Path(game_id).n` | `dashboard_backend/services/games.py` | HERMES_HOME |
| `_self_improvement_json` | 4020-4026 | `def _self_improvement_json(path: Path, default):     try:         if path.exists():             return json.loads(path.r` | `dashboard_backend/services/self_improvement.py` | — |
| `_write_self_improvement_json` | 4029-4031 | `def _write_self_improvement_json(path: Path, data) -> None:     path.parent.mkdir(parents=True, exist_ok=True)     path.` | `dashboard_backend/services/self_improvement.py` | — |
| `_append_self_improvement_audit` | 4034-4046 | `def _append_self_improvement_audit(action: str, details: dict, actor: str = "dashboard") -> dict:     entry = {         ` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_read_self_improvement_audit` | 4049-4060 | `def _read_self_improvement_audit(limit: int = 20) -> list[dict]:     audit_path = SELF_IMPROVEMENT_HOME / "control-audit` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_summarize_validation` | 4063-4084 | `def _summarize_validation(validation: dict) -> tuple[str, float, list[str]]:     status = str(validation.get("status") o` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_read_self_improvement_candidate_events` | 4087-4142 | `def _read_self_improvement_candidate_events(limit: int = 20) -> dict:     """Read the append-only self-improvement candi` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_read_self_improvement_candidate_event_coverage` | 4145-4215 | `def _read_self_improvement_candidate_event_coverage() -> dict:     """Return compact read-only event-ledger replay cover` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_read_step_journal_summary` | 4219-4272 | `def _read_step_journal_summary(path: Path) -> dict:     """Summarize a run's append-only step_journal.jsonl for recovery` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `get_self_improvement_ledger` | 4275-4315 | `def get_self_improvement_ledger(limit: int = 25) -> dict:     runs_dir = SELF_IMPROVEMENT_HOME / "runs"     runs: list[d` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_self_improvement_feature_queue_path` | 4318-4319 | `def _self_improvement_feature_queue_path() -> Path:     return SELF_IMPROVEMENT_HOME / "feature-candidates.jsonl"` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_self_improvement_queue_helper_path` | 4322-4323 | `def _self_improvement_queue_helper_path() -> Path:     return Path.home() / "scripts" / "self-augment" / "self_improveme` | `dashboard_backend/services/self_improvement.py` | — |
| `_load_self_improvement_queue_helper` | 4326-4336 | `def _load_self_improvement_queue_helper():     """Load the canonical queue helper used by research/tournament crons.""" ` | `dashboard_backend/services/self_improvement.py` | — |
| `_normalize_dashboard_candidate_for_strict_queue` | 4339-4371 | `def _normalize_dashboard_candidate_for_strict_queue(candidate: dict) -> dict:     """Map dashboard submissions to the ca` | `dashboard_backend/services/self_improvement.py` | — |
| `_normalize_self_improvement_queue_candidate` | 4374-4407 | `def _normalize_self_improvement_queue_candidate(candidate: dict, *, source_path: str) -> dict:     """Normalize both das` | `dashboard_backend/services/self_improvement.py` | — |
| `_load_self_improvement_jsonl_queue` | 4410-4425 | `def _load_self_improvement_jsonl_queue(path: Path) -> list[dict]:     if not path.exists():         return []     candid` | `dashboard_backend/services/self_improvement.py` | — |
| `_load_self_improvement_legacy_queue` | 4428-4436 | `def _load_self_improvement_legacy_queue(path: Path) -> list[dict]:     data = _self_improvement_json(path, {"candidates"` | `dashboard_backend/services/self_improvement.py` | — |
| `_summarize_self_improvement_queue` | 4439-4447 | `def _summarize_self_improvement_queue(candidates: list[dict]) -> dict:     status_counts: dict[str, int] = {}     target` | `dashboard_backend/services/self_improvement.py` | — |
| `_self_improvement_backlog_gate_summary` | 4450-4498 | `def _self_improvement_backlog_gate_summary(jsonl_path: Path, jsonl_candidates: list[dict]) -> dict:     """Return the ca` | `dashboard_backend/services/self_improvement.py` | — |
| `_load_self_improvement_queue` | 4501-4519 | `def _load_self_improvement_queue() -> dict:     jsonl_path = _self_improvement_feature_queue_path()     legacy_path = SE` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_candidate_for_jsonl_queue` | 4522-4529 | `def _candidate_for_jsonl_queue(candidate: dict) -> dict:     item = dict(candidate or {})     item.setdefault("problem",` | `dashboard_backend/services/self_improvement.py` | — |
| `_candidate_for_dashboard_policy` | 4532-4562 | `def _candidate_for_dashboard_policy(candidate: dict) -> dict:     """Accept either legacy dashboard fields or live JSONL` | `dashboard_backend/services/self_improvement.py` | — |
| `_save_self_improvement_queue` | 4565-4576 | `def _save_self_improvement_queue(data: dict) -> None:     candidates = data.get("candidates", []) if isinstance(data, di` | `dashboard_backend/services/self_improvement.py` | — |
| `_score_self_improvement_candidate` | 4579-4614 | `def _score_self_improvement_candidate(candidate: dict) -> tuple[float, list[str]]:     candidate = _candidate_for_dashbo` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_ALLOWED_LAYERS, SELF_IMPROVEMENT_BANNED_PHRASES |
| `add_self_improvement_candidate` | 4617-4673 | `def add_self_improvement_candidate(candidate: dict) -> dict:     queue = _load_self_improvement_queue()     helper = _lo` | `dashboard_backend/services/self_improvement.py` | — |
| `list_self_improvement_candidates` | 4676-4688 | `def list_self_improvement_candidates() -> dict:     queue = _load_self_improvement_queue()     candidates = sorted(queue` | `dashboard_backend/services/self_improvement.py` | — |
| `select_self_improvement_candidate` | 4691-4720 | `def select_self_improvement_candidate(threshold: float = 5.0) -> dict:     queue = _load_self_improvement_queue()     qu` | `dashboard_backend/services/self_improvement.py` | — |
| `_self_improvement_jobs_path` | 4723-4724 | `def _self_improvement_jobs_path() -> Path:     return HERMES_HOME / "cron" / "jobs.json"` | `dashboard_backend/services/self_improvement.py` | HERMES_HOME |
| `_load_cron_jobs_file` | 4727-4728 | `def _load_cron_jobs_file() -> dict:     return _self_improvement_json(_self_improvement_jobs_path(), {"jobs": []})` | `dashboard_backend/services/cron.py` | — |
| `_iter_cron_jobs` | 4731-4738 | `def _iter_cron_jobs(jobs_data) -> list[dict]:     if isinstance(jobs_data, dict):         jobs = jobs_data.get("jobs", [` | `dashboard_backend/services/cron.py` | — |
| `_cron_job_enabled` | 4741-4742 | `def _cron_job_enabled(job: dict) -> bool:     return bool(job.get("enabled", job.get("state") not in {"paused", "disable` | `dashboard_backend/services/cron.py` | — |
| `_find_self_improvement_job` | 4745-4749 | `def _find_self_improvement_job(jobs_data) -> Optional[dict]:     for job in _iter_cron_jobs(jobs_data):         if job.g` | `dashboard_backend/services/self_improvement.py` | — |
| `get_self_improvement_cron_mesh` | 4752-4813 | `def get_self_improvement_cron_mesh() -> dict:     jobs_data = _load_cron_jobs_file()     jobs = _iter_cron_jobs(jobs_dat` | `dashboard_backend/services/self_improvement.py` | — |
| `get_self_improvement_drift_status` | 4816-4840 | `def get_self_improvement_drift_status() -> dict:     runs_dir = SELF_IMPROVEMENT_HOME / "runs"     latest = None     if ` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `get_self_improvement_supervisor` | 4843-4861 | `def get_self_improvement_supervisor() -> dict:     jobs_data = _load_cron_jobs_file()     job = _find_self_improvement_j` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_save_cron_jobs_file` | 4864-4865 | `def _save_cron_jobs_file(jobs_data: dict) -> None:     _write_self_improvement_json(_self_improvement_jobs_path(), jobs_` | `dashboard_backend/services/cron.py` | — |
| `apply_self_improvement_control` | 4868-4904 | `def apply_self_improvement_control(action: str, confirm: bool = False, actor: str = "dashboard") -> dict:     action = s` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_HOME |
| `_parse_outbox_datetime` | 4907-4921 | `def _parse_outbox_datetime(value: object) -> datetime.datetime | None:     if not value:         return None     text = ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_nonempty_outbox_text` | 4924-4925 | `def _nonempty_outbox_text(value: object) -> bool:     return isinstance(value, str) and bool(value.strip())` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_validate_becomussy_outbox_record` | 4928-4971 | `def _validate_becomussy_outbox_record(record: dict) -> list[str]:     """Mirror the local Becomussy outbox preflight che` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_becomussy_resume_packet_helper_path` | 4974-4975 | `def _becomussy_resume_packet_helper_path() -> Path:     return Path.home() / "scripts" / "self-augment" / "becomussy_res` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_load_becomussy_resume_packet_helper` | 4978-4987 | `def _load_becomussy_resume_packet_helper():     helper_path = _becomussy_resume_packet_helper_path()     if not helper_p` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_json_chars` | 4990-4994 | `def _json_chars(value) -> int:     try:         return len(json.dumps(value, sort_keys=True, default=str))     except Ex` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_fallback_compact_becomussy_resume_packet` | 4997-5042 | `def _fallback_compact_becomussy_resume_packet(packet: dict, *, max_section_chars: int) -> dict:     """Small local fallb` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_compact_becomussy_resume_packet_for_dashboard` | 5045-5054 | `def _compact_becomussy_resume_packet_for_dashboard(packet: dict, *, max_section_chars: int = 12000) -> dict:     helper ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `get_becomussy_resume_packet` | 5057-5091 | `def get_becomussy_resume_packet() -> dict:     """Return the latest Becomussy-backed self-improvement resume packet.    ` | `app.py/bootstrap or dashboard_backend/core/*` | SELF_IMPROVEMENT_HOME |
| `get_becomussy_outbox_health` | 5094-5191 | `def get_becomussy_outbox_health(limit_errors: int = 5) -> dict:     """Summarize queued Becomussy continuity writes with` | `dashboard_backend/services/diagnostics.py` | HERMES_HOME |
| `get_self_improvement_status` | 5194-5212 | `def get_self_improvement_status() -> dict:     cron_mesh = get_self_improvement_cron_mesh()     drift = get_self_improve` | `dashboard_backend/services/self_improvement.py` | SELF_IMPROVEMENT_ALLOWED_LAYERS, SELF_IMPROVEMENT_BANNED_PHRASES |
| `_autonomous_development_home` | 5270-5271 | `def _autonomous_development_home() -> Path:     return HERMES_HOME / "autonomous-development"` | `dashboard_backend/services/autonomous_development.py` | HERMES_HOME |
| `_autonomous_development_registry_path` | 5274-5275 | `def _autonomous_development_registry_path() -> Path:     return _autonomous_development_home() / "pipelines.json"` | `dashboard_backend/services/autonomous_development.py` | — |
| `_autonomous_development_audit_path` | 5278-5279 | `def _autonomous_development_audit_path() -> Path:     return _autonomous_development_home() / "audit.jsonl"` | `dashboard_backend/services/autonomous_development.py` | — |
| `_slugify_pipeline_id` | 5282-5284 | `def _slugify_pipeline_id(name: str) -> str:     slug = re.sub(r"[^a-z0-9]+", "-", str(name or "pipeline").lower()).strip` | `dashboard_backend/services/autonomous_development.py` | — |
| `_read_autonomous_development_audit` | 5287-5298 | `def _read_autonomous_development_audit(limit: int = 30) -> list[dict]:     path = _autonomous_development_audit_path()  ` | `dashboard_backend/services/autonomous_development.py` | — |
| `_append_autonomous_development_audit` | 5301-5313 | `def _append_autonomous_development_audit(action: str, details: dict, actor: str = "dashboard") -> dict:     entry = {   ` | `dashboard_backend/services/autonomous_development.py` | — |
| `_normalize_pipeline_specifications` | 5316-5323 | `def _normalize_pipeline_specifications(data: dict) -> dict:     specs = data.get("specifications") if isinstance(data.ge` | `dashboard_backend/services/autonomous_development.py` | — |
| `_load_autonomous_development_registry` | 5326-5349 | `def _load_autonomous_development_registry() -> dict:     path = _autonomous_development_registry_path()     existing = _` | `dashboard_backend/services/autonomous_development.py` | AUTONOMOUS_DEVELOPMENT_DEFAULT_PIPELINES |
| `_save_autonomous_development_registry` | 5352-5356 | `def _save_autonomous_development_registry(registry: dict) -> None:     registry = dict(registry or {})     registry["ver` | `dashboard_backend/services/autonomous_development.py` | — |
| `_find_autonomous_pipeline` | 5359-5363 | `def _find_autonomous_pipeline(registry: dict, pipeline_id: str) -> Optional[dict]:     for pipeline in registry.get("pip` | `dashboard_backend/services/autonomous_development.py` | — |
| `_jobs_by_name` | 5366-5367 | `def _jobs_by_name() -> dict[str, dict]:     return {str(job.get("name") or ""): job for job in _iter_cron_jobs(_load_cro` | `dashboard_backend/services/cron.py` | — |
| `_pipeline_jobs_summary` | 5370-5395 | `def _pipeline_jobs_summary(pipeline: dict, jobs_by_name: dict[str, dict]) -> dict:     names = [str(name) for name in pi` | `dashboard_backend/services/autonomous_development.py` | — |
| `_hydrate_autonomous_pipeline` | 5398-5409 | `def _hydrate_autonomous_pipeline(pipeline: dict, jobs_by_name: dict[str, dict]) -> dict:     item = dict(pipeline)     i` | `dashboard_backend/services/autonomous_development.py` | — |
| `get_autonomous_development_status` | 5412-5423 | `def get_autonomous_development_status() -> dict:     registry = _load_autonomous_development_registry()     jobs_by_name` | `dashboard_backend/services/autonomous_development.py` | — |
| `create_autonomous_development_pipeline` | 5426-5453 | `def create_autonomous_development_pipeline(data: dict, actor: str = "dashboard") -> dict:     data = data or {}     name` | `dashboard_backend/services/autonomous_development.py` | — |
| `update_autonomous_development_pipeline` | 5456-5493 | `def update_autonomous_development_pipeline(pipeline_id: str, data: dict, actor: str = "dashboard") -> dict:     registry` | `dashboard_backend/services/autonomous_development.py` | — |
| `_schedule_from_display` | 5496-5504 | `def _schedule_from_display(display: str):     text = str(display or "").strip()     match = re.search(r"(\d+)\s*(m|min|m` | `dashboard_backend/services/cron.py` | — |
| `apply_autonomous_development_pipeline_control` | 5507-5543 | `def apply_autonomous_development_pipeline_control(pipeline_id: str, action: str, actor: str = "dashboard") -> dict:     ` | `dashboard_backend/services/autonomous_development.py` | — |
| `get_autonomous_development_endpoint` | 5546-5547 | `async def get_autonomous_development_endpoint(request):     return JSONResponse(get_autonomous_development_status())` | `dashboard_backend/services/autonomous_development.py` | — |
| `create_autonomous_development_pipeline_endpoint` | 5550-5556 | `async def create_autonomous_development_pipeline_endpoint(request):     try:         data = json.loads((await request.bo` | `dashboard_backend/services/autonomous_development.py` | — |
| `update_autonomous_development_pipeline_endpoint` | 5559-5566 | `async def update_autonomous_development_pipeline_endpoint(request):     pipeline_id = request.path_params.get("pipeline_` | `dashboard_backend/services/autonomous_development.py` | — |
| `control_autonomous_development_pipeline_endpoint` | 5569-5576 | `async def control_autonomous_development_pipeline_endpoint(request):     pipeline_id = request.path_params.get("pipeline` | `dashboard_backend/services/autonomous_development.py` | — |
| `get_self_improvement_endpoint` | 5579-5580 | `async def get_self_improvement_endpoint(request):     return JSONResponse(get_self_improvement_status())` | `dashboard_backend/services/self_improvement.py` | — |
| `get_self_improvement_runs_endpoint` | 5583-5584 | `async def get_self_improvement_runs_endpoint(request):     return JSONResponse(get_self_improvement_ledger())` | `dashboard_backend/services/self_improvement.py` | — |
| `get_self_improvement_candidates_endpoint` | 5587-5588 | `async def get_self_improvement_candidates_endpoint(request):     return JSONResponse(list_self_improvement_candidates())` | `dashboard_backend/services/self_improvement.py` | — |
| `create_self_improvement_candidate_endpoint` | 5591-5597 | `async def create_self_improvement_candidate_endpoint(request):     try:         data = json.loads((await request.body())` | `dashboard_backend/services/self_improvement.py` | — |
| `select_self_improvement_candidate_endpoint` | 5600-5601 | `async def select_self_improvement_candidate_endpoint(request):     return JSONResponse(select_self_improvement_candidate` | `dashboard_backend/services/self_improvement.py` | — |
| `control_self_improvement_endpoint` | 5604-5612 | `async def control_self_improvement_endpoint(request):     try:         data = json.loads((await request.body()) or b"{}"` | `dashboard_backend/services/self_improvement.py` | — |
| `get_cron_jobs` | 5615-5623 | `async def get_cron_jobs(request):     async with httpx.AsyncClient(timeout=10.0) as client:         try:             res` | `dashboard_backend/services/cron.py` | API_KEY, HERMES_API |
| `create_cron_job` | 5626-5637 | `async def create_cron_job(request):     body = await request.body()     async with httpx.AsyncClient(timeout=10.0) as cl` | `dashboard_backend/services/cron.py` | API_KEY, HERMES_API |
| `update_cron_job` | 5640-5652 | `async def update_cron_job(request):     job_id = request.path_params["job_id"]     body = await request.body()     async` | `dashboard_backend/services/cron.py` | API_KEY, HERMES_API |
| `delete_cron_job` | 5655-5665 | `async def delete_cron_job(request):     job_id = request.path_params["job_id"]     async with httpx.AsyncClient(timeout=` | `dashboard_backend/services/cron.py` | API_KEY, HERMES_API |
| `pause_cron_job` | 5668-5678 | `async def pause_cron_job(request):     job_id = request.path_params["job_id"]     async with httpx.AsyncClient(timeout=1` | `dashboard_backend/services/cron.py` | API_KEY, HERMES_API |
| `resume_cron_job` | 5681-5691 | `async def resume_cron_job(request):     job_id = request.path_params["job_id"]     async with httpx.AsyncClient(timeout=` | `dashboard_backend/services/cron.py` | API_KEY, HERMES_API |
| `run_cron_job` | 5694-5704 | `async def run_cron_job(request):     job_id = request.path_params["job_id"]     async with httpx.AsyncClient(timeout=10.` | `dashboard_backend/services/cron.py` | API_KEY, HERMES_API |
| `_extract_cron_schedule_name` | 5707-5724 | `def _extract_cron_schedule_name(session_id: str, title: Optional[str]) -> str:     """Extract schedule name from cron se` | `dashboard_backend/services/cron.py` | — |
| `_iso_from_ts` | 5727-5731 | `def _iso_from_ts(ts: Optional[float]) -> Optional[str]:     if ts is None:         return None     dt = datetime.datetim` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_compute_next_run_simple` | 5734-5773 | `def _compute_next_run_simple(cron_expr: str, after: float) -> Optional[float]:     """Minimal cron next-run calculator f` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `get_cron_schedule` | 5776-5857 | `async def get_cron_schedule(request):     db_path = HERMES_HOME / "state.db"     if not db_path.exists():         return` | `dashboard_backend/services/cron.py` | HERMES_HOME |
| `get_secrets` | 5860-5861 | `async def get_secrets(request):     return JSONResponse({"secrets": _build_secrets_payload(get_env())})` | `dashboard_backend/core/config.py` | — |
| `set_secret` | 5864-5882 | `async def set_secret(request):     body = await request.body()     data = json.loads(body)     key = data.get("key")    ` | `dashboard_backend/core/config.py` | — |
| `delete_secret` | 5885-5894 | `async def delete_secret(request):     key = request.path_params["key"]      env = get_env()     if key in env:` | `dashboard_backend/core/config.py` | — |
| `_infer_file_category` | 5902-5946 | `def _infer_file_category(path_str: str) -> str:     """Infer a broad category from a file extension."""     ext = Path(p` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_parse_skill_frontmatter` | 5949-5959 | `def _parse_skill_frontmatter(content: str) -> dict:     """Extract YAML frontmatter from a SKILL.md file."""     if not ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_extract_skill_ids_from_payload` | 5962-5981 | `def _extract_skill_ids_from_payload(payload) -> list[str]:     skill_ids: list[str] = []      def _collect(value):      ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_canonical_skill_id` | 5984-5994 | `def _canonical_skill_id(raw_skill_id: str) -> str:     value = str(raw_skill_id or "").strip().strip("/")     if not val` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_timestamp_to_epoch` | 5997-6015 | `def _timestamp_to_epoch(value) -> Optional[float]:     if value is None or value == "":         return None     if isins` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_session_label` | 6018-6029 | `def _session_label(title, summary, session_id: str) -> str:     clean_title = " ".join(str(title or "").split()).strip()` | `dashboard_backend/services/sessions.py` | — |
| `_get_messages_from_session_files` | 6032-6086 | `def _get_messages_from_session_files(since_ts: Optional[float] = None) -> list[dict]:     """Read session JSON files to ` | `dashboard_backend/services/sessions.py` | HERMES_HOME |
| `get_graph_data` | 6089-6433 | `async def get_graph_data(request):     """     Return nodes and edges for a relationship graph visualization.      Node ` | `dashboard_backend/services/graph.py` | HERMES_HOME |
| `interrupt_session` | 6436-6514 | `async def interrupt_session(request):     session_id = request.path_params["session_id"]     try:         body = await r` | `dashboard_backend/services/sessions.py` | ACTIVE_CHILD_STREAMS, ACTIVE_RUNS, API_KEY, HERMES_API |
| `steer_session` | 6517-6576 | `async def steer_session(request):     session_id = request.path_params["session_id"]     try:         body = await reque` | `dashboard_backend/services/sessions.py` | ACTIVE_CHILD_STREAMS, ACTIVE_SESSION_STEER_MESSAGES, API_KEY, HERMES_API |
| `stop_run` | 6579-6603 | `async def stop_run(request):     run_id = request.path_params["run_id"]     state = ACTIVE_RUNS.get(run_id)     if not s` | `app.py/bootstrap or dashboard_backend/core/*` | ACTIVE_RUNS |
| `session_stream` | 6606-6670 | `async def session_stream(request):     session_id = request.path_params["session_id"]     db_path = HERMES_HOME / "state` | `dashboard_backend/services/sessions.py` | ACTIVE_CHILD_STREAMS, ACTIVE_RUNS, HERMES_HOME |
| `✅ _message_board_db_path` | 6673-6674 | `def _message_board_db_path() -> Path:     return HERMES_HOME / "dashboard_message_board.sqlite3"` | `dashboard_backend/services/message_board.py` | HERMES_HOME |
| `✅ _message_board_now` | 6677-6678 | `def _message_board_now() -> str:     return datetime.datetime.now(datetime.timezone.utc).isoformat()` | `dashboard_backend/services/message_board.py` | — |
| `✅ _message_board_connection` | 6681-6711 | `def _message_board_connection() -> sqlite3.Connection:     db_path = _message_board_db_path()     db_path.parent.mkdir(p` | `dashboard_backend/services/message_board.py` | — |
| `✅ _message_board_row_to_message` | 6714-6722 | `def _message_board_row_to_message(row: sqlite3.Row) -> dict:     return {         "id": row["id"],         "post_id": ro` | `dashboard_backend/services/message_board.py` | — |
| `✅ _load_message_board_post` | 6725-6748 | `def _load_message_board_post(conn: sqlite3.Connection, post_id: str) -> Optional[dict]:     post_row = conn.execute(    ` | `dashboard_backend/services/message_board.py` | — |
| `✅ get_message_board_post` | 6751-6753 | `def get_message_board_post(post_id: str) -> Optional[dict]:     with _message_board_connection() as conn:         return` | `dashboard_backend/services/message_board.py` | — |
| `✅ list_message_board_posts` | 6756-6784 | `def list_message_board_posts(limit: int = 50) -> list[dict]:     with _message_board_connection() as conn:         rows ` | `dashboard_backend/services/message_board.py` | — |
| `✅ add_message_board_reply` | 6787-6814 | `def add_message_board_reply(post_id: str, content: str, author: str = "Hermes", role: str = "assistant") -> dict:     co` | `dashboard_backend/services/message_board.py` | — |
| `✅ add_message_board_user_message` | 6817-6818 | `def add_message_board_user_message(post_id: str, content: str, author: str = "mojo") -> dict:     return add_message_boa` | `dashboard_backend/services/message_board.py` | — |
| `✅ create_message_board_post` | 6821-6857 | `def create_message_board_post(     title: str,     body: str,     author: str = "mojo",     agent_reply: Optional[str] =` | `dashboard_backend/services/message_board.py` | — |
| `_extract_non_stream_chat_content` | 6860-6880 | `def _extract_non_stream_chat_content(payload: dict) -> str:     try:         choices = payload.get("choices") or []     ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_parse_json_object_content` | 6883-6891 | `def _parse_json_object_content(content: str) -> dict:     text = str(content or "").strip()     if text.startswith("```"` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `call_dnd_hermes_json` | 6894-6907 | `async def call_dnd_hermes_json(messages: list[dict], timeout_seconds: float = 90.0) -> dict:     async with httpx.AsyncC` | `dashboard_backend/services/dnd.py` | API_KEY, HERMES_API |
| `generate_message_board_agent_reply` (kept in app.py) | 6910-6948 | Hermes API agent-reply generation for a message-board thread; not extracted with SQLite persistence | `app.py` for now | API_KEY, HERMES_API |
| `get_message_board_posts_endpoint` (kept in app.py) | 6951-6952 | `async def get_message_board_posts_endpoint(request):     return JSONResponse({"posts": list_message_board_posts()})` | `app.py` route wrapper for now | — |
| `get_message_board_post_endpoint` (kept in app.py) | 6955-6961 | `async def get_message_board_post_endpoint(request, post_id: Optional[str] = None):     if post_id is None:         post_` | `app.py` route wrapper for now | — |
| `create_message_board_post_endpoint` (kept in app.py) | 6964-6976 | `async def create_message_board_post_endpoint(request):     data = await request.json()     try:         post = create_me` | `app.py` route wrapper for now | — |
| `create_message_board_message_endpoint` (kept in app.py) | 6979-6994 | `async def create_message_board_message_endpoint(request):     post_id = request.path_params["post_id"]     data = await ` | `app.py` route wrapper for now | — |
| `get_session_tokens` | 6997-7154 | `async def get_session_tokens(request):     session_id = request.path_params["session_id"]     db_path = HERMES_HOME / "s` | `dashboard_backend/services/sessions.py` | HERMES_HOME, MODEL_COST_TABLE, TOKEN_USAGE_FIELDS |
| `_dnd_turn_lock` | 7177-7182 | `def _dnd_turn_lock(campaign_id: str) -> asyncio.Lock:     lock = DND_TURN_LOCKS.get(str(campaign_id))     if lock is Non` | `dashboard_backend/services/dnd.py` | DND_TURN_LOCKS |
| `_dnd_now` | 7185-7186 | `def _dnd_now() -> str:     return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")` | `dashboard_backend/services/dnd.py` | — |
| `_dnd_db_path` | 7189-7190 | `def _dnd_db_path() -> Path:     return HERMES_HOME / "dnd" / "campaigns.sqlite3"` | `dashboard_backend/services/dnd.py` | HERMES_HOME |
| `_dnd_connect` | 7201-7208 | `def _dnd_connect() -> sqlite3.Connection:     db_path = _dnd_db_path()     db_path.parent.mkdir(parents=True, exist_ok=T` | `dashboard_backend/services/dnd.py` | — |
| `_init_dnd_db` | 7211-7332 | `def _init_dnd_db(conn: sqlite3.Connection) -> None:     conn.executescript(         """         CREATE TABLE IF NOT EXIS` | `dashboard_backend/services/dnd.py` | — |
| `_dnd_ensure_columns` | 7335-7339 | `def _dnd_ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:     existing = {row[1] f` | `dashboard_backend/services/dnd.py` | — |
| `_dnd_row_to_dict` | 7342-7386 | `def _dnd_row_to_dict(row) -> dict | None:     if row is None:         return None     item = dict(row)     if "character` | `dashboard_backend/services/dnd.py` | — |
| `_dnd_rows_to_dicts` | 7389-7390 | `def _dnd_rows_to_dicts(rows) -> list[dict]:     return [_dnd_row_to_dict(row) for row in rows]` | `dashboard_backend/services/dnd.py` | — |
| `create_dnd_campaign` | 7393-7418 | `def create_dnd_campaign(name: str, description: str = "", world_metadata: dict | None = None) -> dict:     name = str(na` | `dashboard_backend/services/dnd.py` | — |
| `list_dnd_campaigns` | 7421-7431 | `def list_dnd_campaigns() -> list[dict]:     with _dnd_connect() as conn:         rows = conn.execute(             """   ` | `dashboard_backend/services/dnd.py` | — |
| `get_dnd_campaign` | 7434-7437 | `def get_dnd_campaign(campaign_id: str) -> dict | None:     with _dnd_connect() as conn:         row = conn.execute("SELE` | `dashboard_backend/services/dnd.py` | — |
| `create_dnd_player` | 7440-7457 | `def create_dnd_player(campaign_id: str, name: str, controller_type: str, agent_prompt: str | None = None) -> dict:     i` | `dashboard_backend/services/dnd.py` | DND_CONTROLLER_TYPES |
| `_get_dnd_player` | 7460-7463 | `def _get_dnd_player(player_id: str) -> dict | None:     with _dnd_connect() as conn:         row = conn.execute("SELECT ` | `dashboard_backend/services/dnd.py` | — |
| `list_dnd_players` | 7466-7474 | `def list_dnd_players(campaign_id: str) -> list[dict]:     if not get_dnd_campaign(campaign_id):         raise KeyError("` | `dashboard_backend/services/dnd.py` | — |
| `create_dnd_character` | 7477-7502 | `def create_dnd_character(campaign_id: str, player_id: str | None, name: str, character_sheet: dict | None = None) -> dic` | `dashboard_backend/services/dnd.py` | DND_CHARACTER_KINDS |
| `list_dnd_characters` | 7505-7513 | `def list_dnd_characters(campaign_id: str) -> list[dict]:     if not get_dnd_campaign(campaign_id):         raise KeyErro` | `dashboard_backend/services/dnd.py` | — |
| `update_dnd_scene` | 7516-7529 | `def update_dnd_scene(campaign_id: str, current_scene) -> dict:     campaign = get_dnd_campaign(campaign_id)     if not c` | `dashboard_backend/services/dnd.py` | — |
| `_coerce_dnd_scene_payload` | 7532-7545 | `def _coerce_dnd_scene_payload(current_scene) -> dict:     now = _dnd_now()     if isinstance(current_scene, str):       ` | `dashboard_backend/services/dnd.py` | — |
| `set_dnd_scene_state` | 7548-7559 | `def set_dnd_scene_state(campaign_id: str, current_scene) -> dict:     if not get_dnd_campaign(campaign_id):         rais` | `dashboard_backend/services/dnd.py` | — |
| `append_dnd_event` | 7562-7598 | `def append_dnd_event(     campaign_id: str,     event_type: str,     body: str,     turn_id: str | None = None,` | `dashboard_backend/services/dnd.py` | — |
| `roll_and_record_dnd_dice` | 7601-7618 | `def roll_and_record_dnd_dice(     campaign_id: str,     expression: str,     label: str = "",     actor: str = "",` | `dashboard_backend/services/dnd.py` | — |
| `_validate_dnd_human_actions` | 7621-7630 | `def _validate_dnd_human_actions(players: list[dict], human_actions: dict) -> None:     human_ids = {player["id"] for pla` | `dashboard_backend/services/dnd.py` | — |
| `roll_dnd_dice` | 7632-7647 | `def roll_dnd_dice(expression: str, seed: str | int | None = None) -> dict:     import random      match = re.fullmatch(r` | `dashboard_backend/services/dnd.py` | — |
| `_fallback_subagent_action` | 7650-7653 | `def _fallback_subagent_action(player: dict, turn_number: int) -> str:     prompt = (player.get("agent_prompt") or "").st` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_emit_dnd_turn_progress` | 7656-7662 | `async def _emit_dnd_turn_progress(progress, event_type: str, **payload) -> None:     if progress is None:         return` | `dashboard_backend/services/dnd.py` | — |
| `_serialize_dnd_auto_turn_job` | 7665-7678 | `def _serialize_dnd_auto_turn_job(job: dict) -> dict:     return {         "id": job["id"],         "campaign_id": job["c` | `dashboard_backend/services/cron.py` | — |
| `_record_dnd_auto_turn_job_event` | 7681-7704 | `def _record_dnd_auto_turn_job_event(job: dict, event: dict) -> None:     enriched = dict(event)     enriched.setdefault(` | `dashboard_backend/services/cron.py` | — |
| `_dnd_recent_events_chronological` | 7707-7708 | `def _dnd_recent_events_chronological(campaign_id: str, limit: int = 20) -> list[dict]:     return list(reversed(list_dnd` | `dashboard_backend/services/dnd.py` | — |
| `build_dnd_turn_context` | 7711-7717 | `def build_dnd_turn_context(campaign_id: str) -> dict:     return {         "campaign": get_dnd_campaign(campaign_id),   ` | `dashboard_backend/services/dnd.py` | — |
| `validate_dnd_player_action_response` | 7720-7742 | `def validate_dnd_player_action_response(payload: dict) -> dict:     if not isinstance(payload, dict):         raise Valu` | `dashboard_backend/services/dnd.py` | — |
| `validate_dnd_dm_resolution` | 7745-7780 | `def validate_dnd_dm_resolution(payload: dict) -> dict:     if not isinstance(payload, dict):         raise ValueError("D` | `dashboard_backend/services/dnd.py` | — |
| `fallback_dnd_dm_resolution` | 7783-7785 | `def fallback_dnd_dm_resolution(actions: list[dict]) -> dict:     narration = "The party advances: " + "; ".join(action["` | `dashboard_backend/services/dnd.py` | — |
| `_dnd_prompt_context` | 7788-7798 | `def _dnd_prompt_context(context: dict, turn_number: int) -> str:     return json.dumps(         {             "turn_numb` | `dashboard_backend/services/dnd.py` | — |
| `generate_dnd_subagent_action` | 7801-7871 | `async def generate_dnd_subagent_action(player: dict, context: dict, turn_number: int, progress=None) -> dict:     await ` | `dashboard_backend/services/dnd.py` | — |
| `collect_dnd_turn_actions` | 7874-7892 | `async def collect_dnd_turn_actions(players: list[dict], human_actions: dict, context: dict, turn_number: int, progress=N` | `dashboard_backend/services/dnd.py` | — |
| `generate_dnd_dm_resolution` | 7895-7942 | `async def generate_dnd_dm_resolution(context: dict, actions: list[dict], turn_number: int, progress=None) -> dict:     a` | `dashboard_backend/services/dnd.py` | — |
| `_insert_dnd_event` | 7945-7968 | `def _insert_dnd_event(     conn: sqlite3.Connection,     campaign_id: str,     event_type: str,     body: str,` | `dashboard_backend/services/dnd.py` | — |
| `_apply_dnd_dm_resolution` | 7971-7993 | `def _apply_dnd_dm_resolution(conn: sqlite3.Connection, campaign_id: str, turn_id: str, resolution: dict, source: str) ->` | `dashboard_backend/services/dnd.py` | — |
| `run_dnd_auto_turn` | 7996-7998 | `async def run_dnd_auto_turn(campaign_id: str, human_actions: dict | None = None, progress=None) -> dict:     async with ` | `dashboard_backend/services/dnd.py` | — |
| `_run_dnd_auto_turn_unlocked` | 8001-8104 | `async def _run_dnd_auto_turn_unlocked(campaign_id: str, human_actions: dict | None = None, progress=None) -> dict:     c` | `dashboard_backend/services/dnd.py` | — |
| `list_dnd_events` | 8107-8115 | `def list_dnd_events(campaign_id: str) -> list[dict]:     if not get_dnd_campaign(campaign_id):         raise KeyError("C` | `dashboard_backend/services/dnd.py` | — |
| `_dnd_json_body` | 8118-8127 | `async def _dnd_json_body(request):     try:         data = await request.json()     except Exception:         raise Valu` | `dashboard_backend/services/dnd.py` | — |
| `validate_dnd_character_creation_response` | 8132-8162 | `def validate_dnd_character_creation_response(payload: dict) -> dict:     if not isinstance(payload, dict):         raise` | `dashboard_backend/services/dnd.py` | DND_CHARACTER_KINDS |
| `fallback_dnd_character_creation` | 8165-8185 | `def fallback_dnd_character_creation(campaign_id: str, prompt: str, constraints: dict | None = None) -> dict:     campaig` | `dashboard_backend/services/dnd.py` | — |
| `generate_dnd_character_creation` | 8188-8207 | `async def generate_dnd_character_creation(campaign_id: str, prompt: str, constraints: dict | None = None, player_id: str` | `dashboard_backend/services/dnd.py` | DND_SCHEMA_REGISTRY |
| `create_dnd_world_entity` | 8210-8228 | `def create_dnd_world_entity(campaign_id: str, entity_type: str, name: str, summary: str = "", description: str = "", tag` | `dashboard_backend/services/dnd.py` | DND_WORLD_ENTITY_TYPES |
| `list_dnd_world_entities` | 8231-8239 | `def list_dnd_world_entities(campaign_id: str, entity_type: str | None = None) -> list[dict]:     if not get_dnd_campaign` | `dashboard_backend/services/dnd.py` | — |
| `validate_dnd_world_generation_response` | 8242-8259 | `def validate_dnd_world_generation_response(payload: dict) -> dict:     if not isinstance(payload, dict):         raise V` | `dashboard_backend/services/dnd.py` | — |
| `fallback_dnd_world_generation` | 8262-8276 | `def fallback_dnd_world_generation(campaign_id: str, brief: str, parameters: dict | None = None) -> dict:     campaign = ` | `dashboard_backend/services/dnd.py` | — |
| `generate_dnd_world` | 8279-8306 | `async def generate_dnd_world(campaign_id: str, brief: str = "", parameters: dict | None = None) -> dict:     campaign = ` | `dashboard_backend/services/dnd.py` | DND_SCHEMA_REGISTRY |
| `dnd_campaigns_endpoint` | 8309-8318 | `async def dnd_campaigns_endpoint(request):     method = str(getattr(request, "method", "POST") or "POST").upper()     if` | `dashboard_backend/services/dnd.py` | — |
| `dnd_campaign_detail_endpoint` | 8321-8328 | `async def dnd_campaign_detail_endpoint(request):     campaign_id = getattr(request, "path_params", {}).get("campaign_id"` | `dashboard_backend/services/dnd.py` | — |
| `create_dnd_player_endpoint` | 8331-8345 | `async def create_dnd_player_endpoint(request):     campaign_id = getattr(request, "path_params", {}).get("campaign_id") ` | `dashboard_backend/services/dnd.py` | — |
| `dnd_characters_endpoint` | 8350-8368 | `async def dnd_characters_endpoint(request):     campaign_id = str(getattr(request, "path_params", {}).get("campaign_id")` | `dashboard_backend/services/dnd.py` | — |
| `dnd_character_generate_endpoint` | 8371-8383 | `async def dnd_character_generate_endpoint(request):     campaign_id = str(getattr(request, "path_params", {}).get("campa` | `dashboard_backend/services/dnd.py` | — |
| `dnd_world_entities_endpoint` | 8386-8408 | `async def dnd_world_entities_endpoint(request):     campaign_id = str(getattr(request, "path_params", {}).get("campaign_` | `dashboard_backend/services/dnd.py` | — |
| `dnd_world_generate_endpoint` | 8411-8423 | `async def dnd_world_generate_endpoint(request):     campaign_id = str(getattr(request, "path_params", {}).get("campaign_` | `dashboard_backend/services/dnd.py` | — |
| `dnd_schemas_endpoint` | 8426-8427 | `async def dnd_schemas_endpoint(request):     return JSONResponse({"schemas": DND_SCHEMA_REGISTRY, "bounded_context": {"p` | `dashboard_backend/services/dnd.py` | DND_SCHEMA_REGISTRY |
| `_validate_dnd_auto_turn_start` | 8430-8435 | `def _validate_dnd_auto_turn_start(campaign_id: str, human_actions: dict) -> None:     if not get_dnd_campaign(campaign_i` | `dashboard_backend/services/dnd.py` | — |
| `_run_dnd_auto_turn_job` | 8438-8466 | `async def _run_dnd_auto_turn_job(job_id: str, human_actions: dict) -> None:     job = DND_AUTO_TURN_JOBS.get(job_id)    ` | `dashboard_backend/services/cron.py` | DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN, DND_AUTO_TURN_JOBS |
| `dnd_auto_turn_job_start_endpoint` | 8469-8520 | `async def dnd_auto_turn_job_start_endpoint(request):     campaign_id = str(getattr(request, "path_params", {}).get("camp` | `dashboard_backend/services/cron.py` | DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN, DND_AUTO_TURN_JOBS |
| `dnd_auto_turn_job_status_endpoint` | 8523-8531 | `async def dnd_auto_turn_job_status_endpoint(request):     campaign_id = str(getattr(request, "path_params", {}).get("cam` | `dashboard_backend/services/cron.py` | DND_AUTO_TURN_JOBS |
| `dnd_auto_turn_endpoint` | 8534-8546 | `async def dnd_auto_turn_endpoint(request):     campaign_id = getattr(request, "path_params", {}).get("campaign_id")     ` | `dashboard_backend/services/dnd.py` | — |
| `dnd_campaign_scene_endpoint` | 8549-8559 | `async def dnd_campaign_scene_endpoint(request):     campaign_id = getattr(request, "path_params", {}).get("campaign_id")` | `dashboard_backend/services/dnd.py` | — |
| `dnd_dice_roll_endpoint` | 8562-8578 | `async def dnd_dice_roll_endpoint(request):     campaign_id = getattr(request, "path_params", {}).get("campaign_id")     ` | `dashboard_backend/services/dnd.py` | — |
| `_dnd_event_payload_from_request` | 8581-8592 | `def _dnd_event_payload_from_request(data: dict) -> tuple[str, str, str | None, dict]:     event_type = str(data.get("eve` | `dashboard_backend/services/dnd.py` | — |
| `dnd_campaign_events_endpoint` | 8595-8617 | `async def dnd_campaign_events_endpoint(request):     campaign_id = getattr(request, "path_params", {}).get("campaign_id"` | `dashboard_backend/services/dnd.py` | — |
| `_scrolls_python` | 8643-8645 | `def _scrolls_python(project_root: Path) -> str:     venv_python = project_root / ".venv" / "bin" / "python"     return s` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_safe_config_name` | 8648-8652 | `def _scrolls_safe_config_name(name: str) -> str:     candidate = Path(str(name or "")).name     if candidate != name or ` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_tail` | 8655-8661 | `def _scrolls_tail(path: Path, lines: int = 80) -> list[str]:     try:         if not path.exists():             return [` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_read_yaml_json` | 8664-8670 | `def _scrolls_read_yaml_json(path: Path) -> dict:     try:         with path.open("r") as fh:             value = json.lo` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_lock_active` | 8673-8687 | `def _scrolls_lock_active(project_root: Path) -> bool:     lock_path = project_root / "logs" / "autoresearch.lock"     if` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_data_summary` | 8690-8707 | `def _scrolls_data_summary(project_root: Path) -> dict:     if not project_root.exists():         return {"source": "miss` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_prepared_datasets` | 8710-8724 | `def _scrolls_prepared_datasets(project_root: Path) -> list[dict]:     items = []     meta_paths = []     for root in [pr` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_configs` | 8727-8735 | `def _scrolls_configs(project_root: Path) -> list[dict]:     cfg_dir = project_root / "configs"     if not cfg_dir.exists` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_autoresearch_inventory` | 8738-8811 | `def _scrolls_autoresearch_inventory(project_root: Path) -> dict:     def command_item(title: str, command: str, detail: ` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_artifact_files` | 8814-8835 | `def _scrolls_artifact_files(artifact_dir: str | None, limit: int = 8) -> list[dict]:     if not artifact_dir:         re` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_artifact_preview` | 8838-8869 | `def _scrolls_artifact_preview(project_root: Path, artifact_path: str) -> dict:     runs_root = (project_root / "experime` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_get_nested` | 8872-8878 | `def _scrolls_get_nested(obj: dict, path: tuple[str, ...], default=None):     cur = obj     for part in path:         if ` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_json_key` | 8881-8885 | `def _scrolls_json_key(value: Any) -> str:     try:         return json.dumps(value, sort_keys=True, separators=(",", ":"` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_flatten_config` | 8888-8901 | `def _scrolls_flatten_config(obj: Any, prefix: str = "", out: Optional[dict[str, Any]] = None) -> dict[str, Any]:     if ` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_config_diff` | 8904-8916 | `def _scrolls_config_diff(before: Optional[dict], after: Optional[dict], limit: int = 32) -> list[dict]:     left = _scro` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_run_validation_setup` | 8919-8949 | `def _scrolls_run_validation_setup(run: dict) -> dict:     cfg = run.get("config", {}) if isinstance(run.get("config"), d` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_hypotheses` | 8952-8984 | `def _scrolls_hypotheses(runs_chronological: list[dict], limit: int = 12) -> list[dict]:     projected: list[dict] = []  ` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_experiments` | 8987-9090 | `def _scrolls_experiments(project_root: Path) -> dict:     db_path = project_root / "experiments" / "experiments.db"     ` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_progress_tracker` | 9093-9320 | `def _scrolls_progress_tracker(project_root: Path, data_summary: dict, experiments: dict, console: dict) -> dict:     rec` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_cron_status` | 9323-9331 | `def _scrolls_cron_status(project_root: Path) -> dict:     needle = f"cd {project_root}"     try:         proc = subproce` | `dashboard_backend/services/cron.py` | — |
| `_scrolls_running_processes` | 9334-9360 | `def _scrolls_running_processes(project_root: Path, limit: int = 8) -> list[dict]:     try:         proc = subprocess.run` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_improvement_loop_status` | 9363-9382 | `def _scrolls_improvement_loop_status() -> dict:     try:         mesh = get_self_improvement_cron_mesh()     except Exce` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_console_status` | 9385-9403 | `def _scrolls_console_status(project_root: Path, lines: int = 160) -> dict:     log_path = project_root / "logs" / "autor` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_timed_loop_status` | 9406-9418 | `def _scrolls_timed_loop_status() -> dict:     with _SCROLLS_LOOP_LOCK:         state = dict(_SCROLLS_LOOP_STATE)     if ` | `dashboard_backend/services/scrolls.py` | _SCROLLS_LOOP_LOCK, _SCROLLS_LOOP_STATE |
| `_scrolls_set_loop_state` | 9421-9423 | `def _scrolls_set_loop_state(**updates) -> None:     with _SCROLLS_LOOP_LOCK:         _SCROLLS_LOOP_STATE.update(updates)` | `dashboard_backend/services/scrolls.py` | _SCROLLS_LOOP_LOCK, _SCROLLS_LOOP_STATE |
| `_scrolls_append_loop_log` | 9426-9431 | `def _scrolls_append_loop_log(project_root: Path, message: str) -> None:     logs_dir = project_root / "logs"     logs_di` | `dashboard_backend/services/scrolls.py` | — |
| `_scrolls_timed_loop_worker` | 9434-9482 | `def _scrolls_timed_loop_worker(project_root: Path, duration_minutes: int) -> None:     started = datetime.datetime.now(d` | `dashboard_backend/services/scrolls.py` | _SCROLLS_LOOP_LOCK, _SCROLLS_LOOP_STATE, _SCROLLS_LOOP_STOP |
| `get_scrolls_research_endpoint` | 9485-9505 | `async def get_scrolls_research_endpoint(request):     project_root = _SCROLLS_PROJECT_ROOT     console = _scrolls_consol` | `dashboard_backend/services/scrolls.py` | _SCROLLS_PROJECT_ROOT |
| `get_scrolls_console_endpoint` | 9508-9509 | `async def get_scrolls_console_endpoint(request):     return JSONResponse(_scrolls_console_status(_SCROLLS_PROJECT_ROOT))` | `dashboard_backend/services/scrolls.py` | _SCROLLS_PROJECT_ROOT |
| `get_scrolls_loop_status_endpoint` | 9512-9513 | `async def get_scrolls_loop_status_endpoint(request):     return JSONResponse(_scrolls_timed_loop_status())` | `dashboard_backend/services/scrolls.py` | — |
| `get_scrolls_artifact_endpoint` | 9516-9522 | `async def get_scrolls_artifact_endpoint(request):     try:         return JSONResponse(_scrolls_artifact_preview(_SCROLL` | `dashboard_backend/services/scrolls.py` | _SCROLLS_PROJECT_ROOT |
| `_scrolls_spawn` | 9525-9535 | `def _scrolls_spawn(command: list[str], project_root: Path):     if not project_root.exists():         return JSONRespons` | `dashboard_backend/services/scrolls.py` | — |
| `trigger_scrolls_autoresearch_endpoint` | 9538-9539 | `async def trigger_scrolls_autoresearch_endpoint(request):     return _scrolls_spawn([_scrolls_python(_SCROLLS_PROJECT_RO` | `dashboard_backend/services/scrolls.py` | _SCROLLS_PROJECT_ROOT |
| `start_scrolls_timed_loop_endpoint` | 9542-9561 | `async def start_scrolls_timed_loop_endpoint(request):     try:         body = await request.json()     except Exception:` | `dashboard_backend/services/scrolls.py` | _SCROLLS_LOOP_LOCK, _SCROLLS_LOOP_STATE, _SCROLLS_PROJECT_ROOT |
| `stop_scrolls_timed_loop_endpoint` | 9564-9568 | `async def stop_scrolls_timed_loop_endpoint(request):     _SCROLLS_LOOP_STOP.set()     _scrolls_set_loop_state(status="st` | `dashboard_backend/services/scrolls.py` | _SCROLLS_LOOP_STOP, _SCROLLS_PROJECT_ROOT |
| `run_scrolls_experiment_endpoint` | 9571-9580 | `async def run_scrolls_experiment_endpoint(request):     try:         body = await request.json()         config_name = _` | `dashboard_backend/services/scrolls.py` | _SCROLLS_PROJECT_ROOT |
| `_truncate_update_output` | 9583-9587 | `def _truncate_update_output(text: str, limit: int = 12000) -> str:     text = text or ""     if len(text) <= limit:     ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_run_dashboard_update_command` | 9590-9623 | `def _run_dashboard_update_command(args: list[str], cwd: Path, timeout: int = 120) -> dict:     started = time.time()    ` | `app.py/bootstrap or dashboard_backend/core/*` | — |
| `_dashboard_auto_update` | 9626-9706 | `def _dashboard_auto_update(allow_dirty: bool = False, install_dependencies: bool = True) -> tuple[int, dict]:     root =` | `app.py/bootstrap or dashboard_backend/core/*` | DASHBOARD_REPO_ROOT |
| `dashboard_auto_update_endpoint` | 9709-9717 | `async def dashboard_auto_update_endpoint(request):     try:         body = await request.json()     except Exception:   ` | `app.py/bootstrap or dashboard_backend/core/*` | — |

## Route registry and groups
| Line | Kind | Path | Endpoint | Methods |
|---:|---|---|---|---|
| 9726 | Route | `"/"` | `homepage)` | `—` |
| 9731 | Route | `"/dnd"` | `homepage)` | `—` |
| 9732 | Route | `"/dnd/"` | `homepage)` | `—` |
| 9733 | Route | `"/dnd/popout"` | `homepage)` | `—` |
| 9734 | Route | `"/campaigns"` | `homepage)` | `—` |
| 9735 | Route | `"/campaigns/"` | `homepage)` | `—` |
| 9736 | Route | `"/chat"` | `chat_stream` | `"POST"` |
| 9737 | Route | `"/api/runs/{run_id}/stop"` | `stop_run` | `"POST"` |
| 9738 | Route | `"/api/dashboard-state/{key}"` | `get_dashboard_state)` | `—` |
| 9739 | Route | `"/api/dashboard-state/{key}"` | `set_dashboard_state` | `"PUT"` |
| 9740 | Route | `"/api/dashboard-state/{key}"` | `delete_dashboard_state` | `"DELETE"` |
| 9741 | Route | `"/api/dashboard/update"` | `dashboard_auto_update_endpoint` | `"POST"` |
| 9742 | Route | `"/health"` | `health)` | `—` |
| 9743 | Route | `"/api/status"` | `get_status)` | `—` |
| 9744 | Route | `"/api/config"` | `get_config_endpoint)` | `—` |
| 9745 | Route | `"/api/settings"` | `get_settings)` | `—` |
| 9746 | Route | `"/api/config"` | `update_config` | `"POST"` |
| 9747 | Route | `"/api/models"` | `get_models)` | `—` |
| 9748 | Route | `"/api/personalities"` | `get_personalities)` | `—` |
| 9749 | Route | `"/api/personality"` | `set_personality` | `"POST"` |
| 9750 | Route | `"/api/model"` | `set_model` | `"POST"` |
| 9751 | Route | `"/api/agent-observability"` | `get_agent_observability_endpoint)` | `—` |
| 9752 | Route | `"/api/token-usage"` | `get_token_usage_endpoint)` | `—` |
| 9753 | Route | `"/api/sessions"` | `get_sessions)` | `—` |
| 9754 | Route | `"/api/sessions/search"` | `search_sessions)` | `—` |
| 9755 | Route | `"/api/sessions/sources"` | `get_session_sources)` | `—` |
| 9766 | Route | `"/api/sessions/{session_id}"` | `get_session)` | `—` |
| 9767 | Route | `"/api/sessions/{session_id}/files"` | `get_session_files)` | `—` |
| 9768 | Route | `"/api/sessions/{session_id}/tokens"` | `get_session_tokens)` | `—` |
| 9769 | Route | `"/api/sessions/{session_id}/stream"` | `session_stream)` | `—` |
| 9775 | Route | `"/api/sessions/{session_id}/steer"` | `steer_session` | `"POST"` |
| 9776 | Route | `"/api/sessions/{session_id}"` | `delete_session` | `"DELETE"` |
| 9777 | Route | `"/api/message-board"` | `get_message_board_posts_endpoint)` | `—` |
| 9778 | Route | `"/api/message-board"` | `create_message_board_post_endpoint` (kept in app.py) | `"POST"` |
| 9784 | Route | `"/api/message-board/{post_id}"` | `get_message_board_post_endpoint)` | `—` |
| 9785 | Route | `"/api/files/content"` | `get_file_content)` | `—` |
| 9786 | Route | `"/api/memory"` | `get_memory)` | `—` |
| 9787 | Route | `"/api/memory"` | `update_memory` | `"POST"` |
| 9788 | Route | `"/api/skills"` | `get_skills)` | `—` |
| 9789 | Route | `"/api/skills/toggle"` | `toggle_skill` | `"POST"` |
| 9790 | Route | `"/api/skills/{skill_id}/content"` | `get_skill_content)` | `—` |
| 9791 | Route | `"/api/games"` | `get_games_endpoint)` | `—` |
| 9792 | Route | `"/api/games/{game_id}/content"` | `get_game_content_endpoint)` | `—` |
| 9793 | Route | `"/api/pokemon/restart"` | `restart_pokemon_endpoint` | `"POST"` |
| 9794 | Route | `"/api/diagnostics/context"` | `diagnostics_context_endpoint)` | `—` |
| 9795 | Route | `"/api/dnd/campaigns"` | `dnd_campaigns_endpoint` | `"GET", "POST"` |
| 9796 | Route | `"/api/dnd/schemas"` | `dnd_schemas_endpoint)` | `—` |
| 9797 | Route | `"/api/dnd/campaigns/{campaign_id}"` | `dnd_campaign_detail_endpoint)` | `—` |
| 9798 | Route | `"/api/dnd/campaigns/{campaign_id}/players"` | `create_dnd_player_endpoint` | `"POST"` |
| 9799 | Route | `"/api/dnd/campaigns/{campaign_id}/characters"` | `dnd_characters_endpoint` | `"GET", "POST"` |
| 9800 | Route | `"/api/dnd/campaigns/{campaign_id}/characters/generate"` | `dnd_character_generate_endpoint` | `"POST"` |
| 9801 | Route | `"/api/dnd/campaigns/{campaign_id}/world/entities"` | `dnd_world_entities_endpoint` | `"GET", "POST"` |
| 9802 | Route | `"/api/dnd/campaigns/{campaign_id}/world/generate"` | `dnd_world_generate_endpoint` | `"POST"` |
| 9803 | Route | `"/api/dnd/campaigns/{campaign_id}/turns/auto"` | `dnd_auto_turn_endpoint` | `"POST"` |
| 9804 | Route | `"/api/dnd/campaigns/{campaign_id}/turns/auto/jobs"` | `dnd_auto_turn_job_start_endpoint` | `"POST"` |
| 9805 | Route | `"/api/dnd/campaigns/{campaign_id}/turns/auto/jobs/{job_id}"` | `dnd_auto_turn_job_status_endpoint)` | `—` |
| 9806 | Route | `"/api/dnd/campaigns/{campaign_id}/scene"` | `dnd_campaign_scene_endpoint` | `"PATCH", "POST"` |
| 9807 | Route | `"/api/dnd/campaigns/{campaign_id}/dice"` | `dnd_dice_roll_endpoint` | `"POST"` |
| 9808 | Route | `"/api/dnd/campaigns/{campaign_id}/events"` | `dnd_campaign_events_endpoint` | `"GET", "POST"` |
| 9809 | Route | `"/doom/"` | `doom_watch_proxy_endpoint` | `"GET", "POST"` |
| 9810 | Route | `"/doom/{path:path}"` | `doom_watch_proxy_endpoint` | `"GET", "POST"` |
| 9811 | Route | `"/minihack/"` | `minihack_watch_proxy_endpoint` | `"GET", "POST"` |
| 9812 | Route | `"/minihack/{path:path}"` | `minihack_watch_proxy_endpoint` | `"GET", "POST"` |
| 9813 | Route | `"/pokemon/chat"` | `chat_stream` | `"POST"` |
| 9814 | Route | `"/pokemon/api/diagnostics/context"` | `diagnostics_context_endpoint)` | `—` |
| 9815 | Route | `"/pokemon/"` | `pokemon_proxy_endpoint` | `"GET", "POST"` |
| 9816 | Route | `"/pokemon/{path:path}"` | `pokemon_proxy_endpoint` | `"GET", "POST"` |
| 9817 | Route | `"/api/self-improvement"` | `get_self_improvement_endpoint)` | `—` |
| 9818 | Route | `"/api/autonomous-development"` | `get_autonomous_development_endpoint)` | `—` |
| 9819 | Route | `"/api/scrolls/research"` | `get_scrolls_research_endpoint)` | `—` |
| 9820 | Route | `"/api/scrolls/console"` | `get_scrolls_console_endpoint)` | `—` |
| 9821 | Route | `"/api/scrolls/loop/status"` | `get_scrolls_loop_status_endpoint)` | `—` |
| 9822 | Route | `"/api/scrolls/artifact"` | `get_scrolls_artifact_endpoint)` | `—` |
| 9823 | Route | `"/api/scrolls/autoresearch/trigger"` | `trigger_scrolls_autoresearch_endpoint` | `"POST"` |
| 9824 | Route | `"/api/scrolls/autoresearch/loop/start"` | `start_scrolls_timed_loop_endpoint` | `"POST"` |
| 9825 | Route | `"/api/scrolls/autoresearch/loop/stop"` | `stop_scrolls_timed_loop_endpoint` | `"POST"` |
| 9826 | Route | `"/api/scrolls/experiments/run"` | `run_scrolls_experiment_endpoint` | `"POST"` |
| 9827 | Route | `"/api/autonomous-development/pipelines"` | `create_autonomous_development_pipeline_endpoint` | `"POST"` |
| 9828 | Route | `"/api/autonomous-development/pipelines/{pipeline_id}"` | `update_autonomous_development_pipeline_endpoint` | `"PATCH"` |
| 9829 | Route | `"/api/autonomous-development/pipelines/{pipeline_id}/control"` | `control_autonomous_development_pipeline_endpoint` | `"POST"` |
| 9830 | Route | `"/api/self-improvement/runs"` | `get_self_improvement_runs_endpoint)` | `—` |
| 9831 | Route | `"/api/self-improvement/candidates"` | `get_self_improvement_candidates_endpoint)` | `—` |
| 9832 | Route | `"/api/self-improvement/candidates"` | `create_self_improvement_candidate_endpoint` | `"POST"` |
| 9833 | Route | `"/api/self-improvement/candidates/select"` | `select_self_improvement_candidate_endpoint` | `"POST"` |
| 9834 | Route | `"/api/self-improvement/control"` | `control_self_improvement_endpoint` | `"POST"` |
| 9835 | Route | `"/api/cron"` | `get_cron_jobs)` | `—` |
| 9836 | Route | `"/api/cron"` | `create_cron_job` | `"POST"` |
| 9837 | Route | `"/api/cron/schedule"` | `get_cron_schedule)` | `—` |
| 9838 | Route | `"/api/cron/{job_id}"` | `update_cron_job` | `"PATCH"` |
| 9839 | Route | `"/api/cron/{job_id}"` | `delete_cron_job` | `"DELETE"` |
| 9840 | Route | `"/api/cron/{job_id}/pause"` | `pause_cron_job` | `"POST"` |
| 9841 | Route | `"/api/cron/{job_id}/resume"` | `resume_cron_job` | `"POST"` |
| 9842 | Route | `"/api/cron/{job_id}/run"` | `run_cron_job` | `"POST"` |
| 9843 | Route | `"/api/secrets"` | `get_secrets)` | `—` |
| 9844 | Route | `"/api/secrets"` | `set_secret` | `"POST"` |
| 9845 | Route | `"/api/secrets/{key}"` | `delete_secret` | `"DELETE"` |
| 9846 | Route | `"/api/graph"` | `get_graph_data)` | `—` |
| 9850 | WebSocketRoute | `"/pokemon/ws"` | `WebSocketRoute("/pokemon/ws"` | `—` |
| 9851 | WebSocketRoute | `"/pokemon/watch/ws"` | `WebSocketRoute("/pokemon/watch/ws"` | `—` |

## Risk flags
### Global mutable state
- `HERMES_AGENT_PATH` at line 75
- `HERMES_API` at line 274
- `HERMES_HOME` at line 275
- `DASHBOARD_REPO_ROOT` at line 276
- `SELF_IMPROVEMENT_HOME` at line 279
- `API_KEY` at line 282
- `DASHBOARD_PORT` at line 285
- `HERMES_READ_TIMEOUT_RAW` at line 286
- `HERMES_READ_TIMEOUT` at line 287
- `HERMES_USEFUL_EVENT_TIMEOUT` at line 292
- `ACTIVE_RUN_TTL_SECONDS` at line 301
- `ACTIVE_RUNS` at line 302
- `ACTIVE_CHILD_STREAMS` at line 303
- `ACTIVE_SESSION_STEER_MESSAGES` at line 304
- `_STARTUP_METADATA_BACKFILL_STARTED` at line 305
- `DASHBOARD_STATE_DB_PATH` at line 306
- `DASHBOARD_STATE_KEYS` at line 307
- `DASHBOARD_STATE_LOCK` at line 308
- `INTERRUPT_FLAGS` at line 313
- `BUILT_IN_PERSONALITIES` at line 323
- `EXTRA_SECRET_METADATA` at line 340
- `WEB_BACKENDS` at line 385
- `TTS_PROVIDERS` at line 386
- `STT_PROVIDERS` at line 387
- `BUSY_INPUT_MODES` at line 388
- `TOOL_PROGRESS_MODES` at line 389
- `BACKGROUND_NOTIFICATION_MODES` at line 390
- `RESUME_DISPLAY_MODES` at line 391
- `APPROVAL_MODES` at line 392
- `REASONING_EFFORTS` at line 393
- `MODEL_COST_TABLE` at line 396
- `TOKEN_USAGE_FIELDS` at line 2295
- `SKILL_DESCRIPTIONS` at line 3152
- `SKILL_DESCRIPTIONS` at line 3200
- `DOOM_WATCH_SERVER_URL` at line 3457
- `MINIHACK_WATCH_SERVER_URL` at line 3458
- `POKEMON_SERVER_URL` at line 3459
- `POKEMON_AGENT_ROOT` at line 3460
- `POKEMON_ROM_PATH` at line 3461
- `POKEMON_DATA_DIR` at line 3462
- `POKEMON_LOG_DIR` at line 3463
- `SELF_IMPROVEMENT_ALLOWED_LAYERS` at line 3999
- `SELF_IMPROVEMENT_BANNED_PHRASES` at line 4009
- `AUTONOMOUS_DEVELOPMENT_DEFAULT_PIPELINES` at line 5215
- `DND_CONTROLLER_TYPES` at line 7157
- `DND_CHARACTER_KINDS` at line 7158
- `DND_WORLD_ENTITY_TYPES` at line 7159
- `DND_SCHEMA_REGISTRY` at line 7160
- `DND_TURN_LOCKS` at line 7171
- `DND_AUTO_TURN_JOBS` at line 7172
- `DND_ACTIVE_AUTO_TURN_JOB_BY_CAMPAIGN` at line 7173
- `DND_AUTO_TURN_JOB_TTL_SECONDS` at line 7174
- `_SCROLLS_PROJECT_ROOT` at line 8624
- `_SCROLLS_LOOP_LOCK` at line 8628
- `_SCROLLS_LOOP_STOP` at line 8629
- `_SCROLLS_LOOP_STATE` at line 8630
- `routes` at line 9720
- `app` at line 9853

### Routes that mutate filesystem/cron/jobs
- Self-improvement candidate/control routes write queue/audit/lock/cron state.
- Autonomous-development pipeline create/update/control writes registry/audit/cron state.
- Cron POST/PATCH/DELETE/pause/resume/run mutates scheduler state.
- Pokemon save/load/control and game proxy routes may touch emulator/process files.
- Message board POST/DELETE writes SQLite state.
- Dashboard state POST writes SQLite state.
- Settings/personality/secrets/model routes may write configuration files.

### Functions touching 4+ shared globals
- `_run_chat_stream_sync` (644-757) touches 5 globals: ACTIVE_RUNS, API_KEY, HERMES_API, HERMES_READ_TIMEOUT, HERMES_USEFUL_EVENT_TIMEOUT
- `_run_chat_stream` (760-889) touches 5 globals: ACTIVE_RUNS, API_KEY, HERMES_API, HERMES_READ_TIMEOUT, HERMES_USEFUL_EVENT_TIMEOUT
- `_settings_payload` (1867-1941) touches 10 globals: APPROVAL_MODES, BACKGROUND_NOTIFICATION_MODES, BUILT_IN_PERSONALITIES, BUSY_INPUT_MODES, REASONING_EFFORTS, RESUME_DISPLAY_MODES, STT_PROVIDERS, TOOL_PROGRESS_MODES, TTS_PROVIDERS, WEB_BACKENDS
- `_start_pokemon_processes` (3603-3654) touches 5 globals: POKEMON_AGENT_ROOT, POKEMON_DATA_DIR, POKEMON_LOG_DIR, POKEMON_ROM_PATH, POKEMON_SERVER_URL
- `interrupt_session` (6436-6514) touches 4 globals: ACTIVE_CHILD_STREAMS, ACTIVE_RUNS, API_KEY, HERMES_API
- `steer_session` (6517-6576) touches 4 globals: ACTIVE_CHILD_STREAMS, ACTIVE_SESSION_STEER_MESSAGES, API_KEY, HERMES_API

### Circular dependency risks
- Active-run/chat streaming code currently mixes endpoint parsing, child-stream event routing, session ledgers, model/provider config, and frontend projections; extract only after service ownership is designed.
- Config/settings helpers are used by many contexts; move to `core/config.py` before route modules import them broadly.
- Cron controls are shared by self-improvement and autonomous-development; avoid both services importing each other by keeping cron mutation primitives in `services/cron.py`.
- Graph/session/memory functions can form cycles if graph service imports session projections while sessions import graph filters.

### Frontend/static asset route dependencies
- `/static/js/dashboard.js` remains classic compatibility source; do not switch to modules while inline handlers/global functions remain.
- Preserve DOM IDs, CSS classes, route paths, and tab metadata while moving backend wrappers.
- `/static`, `/static/js/dashboard.js`, and `/static/css/dashboard.css` are smoke-test contracts.

## Completed extraction passes
- `dashboard_backend/services/dashboard_state.py`: dashboard-state SQLite ledger/projection persistence is extracted; app-level wrappers preserve `DASHBOARD_STATE_DB_PATH`, `DASHBOARD_STATE_KEYS`, and lock monkeypatch seams. Gate: `python -m pytest tests/test_dashboard_state_persistence.py`.
- `dashboard_backend/services/token_usage.py`: token usage aggregation and projection helpers are extracted; `/api/token-usage` and app-level helper names remain as wrappers. Gate: `python -m pytest tests/test_token_usage_dashboard.py`.
- `dashboard_backend/services/message_board.py`: message-board SQLite post/message persistence is extracted; `/api/message-board*` endpoint wrappers and `generate_message_board_agent_reply` remain in `app.py`. Gate: `python -m pytest tests/test_message_board.py`.
- `dashboard_backend/services/scrolls.py`: read-only Scrolls snapshot projection delegation is extracted; `GET /api/scrolls/snapshot` is restored as a parity API route while app-owned `_SCROLLS_PROJECT_ROOT` remains injected by the wrapper. Gate: `python -m pytest tests/test_scrolls_snapshot.py tests/test_scrolls_panel_navigation.py`.
- `dashboard_backend/services/games_catalog.py`: read-only Games tab skill catalog/frontmatter projection is extracted; `/api/games` remains wrapped in `app.py` and app-owned `HERMES_HOME` is injected at call time. Gate: `python -m pytest tests/test_games_catalog_service.py tests/test_games_tab.py`.
- Self-improvement repair/anomaly read-only parity: `app.py` now surfaces bounded `repair_hint` / `event_coverage_repair_hint` projections and `static/js/dashboard.js` renders Repair Readiness, Anomaly Samples, and inert Next repair commands. Gate: `python -m pytest tests/test_self_improvement_panel.py`.

## Self-improvement repair/anomaly parity pass

### Task frame
Restore the reference dashboard's read-only repair/anomaly visibility for self-improvement candidate event coverage without enabling event-ledger mutations or making experimental tabs default-visible.

### Vocabulary map
- **API route:** existing `GET /api/self-improvement`; no new route was added.
- **Service/projection helper:** `_bounded_candidate_event_repair_hint`, a bounded read-only projection adapter around the canonical self-improvement queue helper's repair hint.
- **Event:** append-only candidate lifecycle ledger row used to derive coverage, anomaly, and readiness projections.
- **State:** `repair_hint` / `event_coverage_repair_hint` are UI state projections; they contain commands as inert text, not executable dashboard jobs.
- **Workflow:** operator reviews repair readiness and next commands outside the dashboard mutation surface.

### Structural model
`_read_self_improvement_candidate_event_coverage()` still delegates replay to the canonical queue helper when available. If coverage is incomplete, it now asks the helper's `backlog_gate(...)` for a bounded repair projection and attaches both `repair_hint` and `event_coverage_repair_hint`. Frontend rendering remains in the classic compatibility script.

### Change set
- Added `_bounded_candidate_event_repair_hint(...)` with sample/anomaly/command bounds and `mutation: False` projection semantics.
- Wired repair projections into `_read_self_improvement_candidate_event_coverage()` for canonical replay results.
- Updated `renderSelfImprovementEventCoverage()` to show Repair Readiness, Anomaly Samples, and Next repair commands as inert text.
- Expanded `tests/test_self_improvement_panel.py` for repair hint projection, anomaly/apply-readiness command surfacing, and frontend marker coverage.
- Updated `docs/self-improvement-autonomous-shipping-plan.md` drift audit.

### Drift audit
- Fixed true retained-surface gap: self-improvement repair/anomaly read-only visibility.
- Still not default-visible: `self-improvement` and `autonomous-development` remain gated by the shipping plan.
- Remaining side-effectful gated gaps include dashboard/backend restart routes.
- Optional/reference-only gaps remain Dashboard Chat IRC bridge, Voice/OmniVoice, and Roguelike/Hermes Labyrinth.

### Next step
After this pass is committed and clean, resume low-risk modular cleanup with dashboard-state route-wrapper extraction using injected app compatibility wrappers.

## Games catalog extraction pass

### Task frame
Extract the low-risk Games tab catalog projection from `app.py` while preserving the `/api/games` API route, payload shape, and all Doom/MiniHack/Pokemon proxy/process surfaces in the app orchestrator.

### Vocabulary map
- **API route:** `GET /api/games`, the external route that returns the dashboard Games catalog projection.
- **Service:** `dashboard_backend/services/games_catalog.py`, bounded read-only filesystem/frontmatter projection logic for gaming skills.
- **Message:** not involved; catalog entries are skill metadata records, not chat/forum/IRC messages.
- **State:** catalog response is a derived projection over `HERMES_HOME/skills/gaming`, not a durable ledger and not mutable runtime state.
- **Workflow:** user opens the Games tab and sees available gaming tools; watch/proxy/restart workflows remain separate and were not moved.

### Structural model
`app.py` imports service implementations as `_parse_game_skill_frontmatter_impl`, `_categorize_game_skill_impl`, and `_get_games_catalog_impl`. Compatibility wrappers keep the old app-level helper names and inject live `HERMES_HOME`; `get_games_endpoint` and route registration are unchanged.

### Change set
- Added `dashboard_backend/services/games_catalog.py` with frontmatter parsing, category inference, and catalog projection helpers.
- Replaced the app-level Games helper bodies with compatibility delegates.
- Added `tests/test_games_catalog_service.py` to validate injected-root behavior, invalid-frontmatter tolerance, and no `app.py` import direction.

### Drift audit
- No public route, DOM, CSS, JavaScript, or payload-shape changes intended.
- `/api/games` remains compatible and existing proxy routes remain untouched.
- Games proxy/process contexts (`/doom/*`, `/minihack/*`, `/pokemon/*`, `/api/pokemon/restart`, `/pokemon/chat`) remain in `app.py` for separate design/gating.

### Next step
After this pass is committed and clean, the safest remaining low-risk refactor pass is dashboard-state route-wrapper extraction using injected app compatibility wrappers. The highest-value remaining parity pass is still self-improvement repair/anomaly read-only projection.

## Scrolls snapshot parity pass

### Task frame
Restore the retained Vesuvius/Scrolls panel's missing read-only snapshot API route without changing existing Scrolls mutating routes, frontend tab visibility, or active loop state ownership.

### Vocabulary map
- **API route:** `GET /api/scrolls/snapshot`, the external HTTP contract added back to the refactor copy.
- **Service:** `dashboard_backend/services/scrolls.py`, bounded read-only delegation logic that imports and calls the standalone `research_dashboard.snapshot.build_snapshot` implementation.
- **State:** the snapshot response is a state projection derived by the Vesuvius research dashboard package from filesystem/database/artifact ledgers under the injected Scrolls project root.
- **Workflow:** existing Scrolls operator workflow can read the snapshot projection; no repair, run, restart, or loop mutation is triggered by this route.

### Structural model
`app.py` imports `ScrollsSnapshotUnavailable` and `_build_scrolls_snapshot_impl`, keeps the route wrapper, injects `_SCROLLS_PROJECT_ROOT`, and returns parity status envelopes (`200`, `503` unavailable, `500` build failure). The service does not import `app.py`.

### Change set
- Added `dashboard_backend/services/scrolls.py` with `build_scrolls_snapshot(project_root)` and `ScrollsSnapshotUnavailable`.
- Added `get_scrolls_snapshot_endpoint` and registered `Route("/api/scrolls/snapshot", ...)`.
- Added `tests/test_scrolls_snapshot.py` for service delegation, object-shape guard, route registration, and wrapper error envelopes.

### Drift audit
- Fixed true retained-surface gap: `GET /api/scrolls/snapshot`.
- Remaining true retained-surface gap: self-improvement repair/anomaly projection UI/tests.
- Remaining side-effectful gated gaps: dashboard/backend restart routes.
- Optional/reference-only gaps remain Dashboard Chat IRC bridge, Voice/OmniVoice, and Roguelike/Hermes Labyrinth.

### Next step
After this pass is committed and the tree is clean, the safest modular pass is dashboard-state route-wrapper extraction, followed by games catalog-only service extraction or self-improvement repair/anomaly read-only projection parity.

## Compatibility wrapper policy
- Keep legacy `app.py` function names while tests or callers import/monkeypatch them directly.
- Pass mutable app-owned dependencies (`HERMES_HOME`, DB paths, locks, config) into services at call time.
- Services must not import `app.py`; planned route modules should depend on services/core only.
- Treat persistent records as ledgers and route/UI summaries as projections so extraction does not change public payload contracts.

## Extraction order
1. ✅ Token usage service (`dashboard_backend/services/token_usage.py`): low-risk read-only aggregation leaf; `/api/token-usage` wrapper remains in `app.py`.
2. ✅ Message board service (`dashboard_backend/services/message_board.py`): isolated SQLite CRUD; route wrappers remain in `app.py` for this pass.
3. Dashboard state route wrappers: service already extracted; move route wrappers after confirming persistence tests stay green and using injected app wrappers.
4. Games catalog-only or Scrolls snapshot/read-only projections where filesystem/proxy state is isolated and route contracts are covered.
5. Config/settings core extraction, then route modules that need it.
6. Self-improvement/autonomous-development only after safety/readiness plan and mutation gates are mapped; route extraction can precede default-visible shipping but must preserve hidden-by-default posture.
7. Child stream / active run backend last among large contexts due to high global mutable state and streaming coupling.

## Drift audit from read-only reference
- Reference has 124 route declarations; refactor has 104 plus extracted static mount in the last parity count. Missing reference surfaces include dashboard restart/backend restart, Dashboard Chat IRC bridge, Voice/OmniVoice routes, and optional/local experiment panels.
- Completed true retained-surface parity gaps: Scrolls snapshot and self-improvement repair/anomaly read-only visibility.
- Dashboard/backend restart routes are real parity gaps but require explicit mutation intent gates.
- Treat Dashboard Chat IRC bridge, OmniVoice/Voice, and Roguelike/Hermes Labyrinth as optional/reference experiments unless explicitly requested.
- Tests parity before this pass: reference had 18 test files / 118 tests; refactor had 17 files / 114 tests plus refactor-specific static/execution/chat sanitizer coverage.

## Next step
Start the next pass from a clean tree. Safest options are dashboard-state route-wrapper extraction using injected app wrappers, or games catalog-only extraction. Do not extract active-run/chat-stream/child-stream until ownership/state design and tests are updated.
