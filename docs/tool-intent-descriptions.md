# Tool Intent Descriptions

Hermes Dashboard can replace the duplicated command text in a tool card header with a short description of what the tool call is intended to do. The full command or code remains available in the expanded tool details.

## Supported Tools

| Tool | Description source | Model request |
|---|---|---|
| `terminal` | Hermes Codex | Yes |
| `execute_code` | Hermes Codex | Yes |
| `read_file` | Deterministic browser text | No |
| `write_file` | Deterministic browser text | No |
| `patch` | Deterministic browser text | No |
| `todo` | Deterministic browser text | No |

Other tools continue to use the dashboard's existing summaries.

Descriptions are optional enrichment. Tool cards render immediately, show an analyzing message while a request is active, and fall back to local text if the request fails, times out, or is rate-limited.

## Requirements

Generated terminal and code descriptions require:

- a Hermes install that includes `agent.auxiliary_client.resolve_provider_client`
- the dashboard process to use the Hermes Python runtime or an environment containing its dependencies
- a valid Hermes-managed OpenAI Codex OAuth login
- access to `gpt-5.6-luna` through that Codex account

Authenticate through Hermes, not through the dashboard:

```sh
hermes auth add openai-codex
```

You can also run `hermes model` and choose **ChatGPT or Codex Subscription**. Hermes stores the login in its own auth store, normally `~/.hermes/auth.json`. Do not place an OAuth access or refresh token in the dashboard repo, `.env.local`, or browser storage.

The main Hermes chat model does not need to be Luna. Tool intent descriptions use their own fixed route.

## Dashboard Configuration

The installer normally writes these paths to `.env.local`:

```sh
HERMES_HOME="$HOME/.hermes"
HERMES_AGENT_PATH="$HOME/.hermes/hermes-agent"
HERMES_VENV="$HOME/.hermes/hermes-agent/venv"
```

Use paths that belong to the same Hermes installation and authentication store. After changing them, restart the dashboard process or user service.

For a manual native launch, use the Hermes virtualenv:

```sh
HERMES_HOME="$HOME/.hermes" \
HERMES_AGENT_PATH="$HOME/.hermes/hermes-agent" \
HERMES_VENV="$HOME/.hermes/hermes-agent/venv" \
"$HOME/.hermes/hermes-agent/venv/bin/python" -m uvicorn app:app \
  --host 127.0.0.1 --port 8081
```

### Fixed Settings

The current release intentionally does not expose provider, model, prompt, or limit overrides. The backend uses:

- provider: `openai-codex`
- model: `gpt-5.6-luna`
- model timeout: 10 seconds
- concurrency: 2 active requests per dashboard process
- rate limit: 60 accepted requests per minute per dashboard process
- maximum request body: 256 KiB
- maximum accepted description: 500 characters

There is no supported `TOOL_INTENT_MODEL`, `TOOL_INTENT_PROVIDER`, or browser-side API key setting. The fixed route prevents a failed Luna request from silently sending command data to another provider or model.

## Docker

The generated-description path needs Hermes' Python runtime dependencies in the dashboard process. The stock standalone dashboard image mounts the Hermes source and home directories, but it may not contain every dependency from the Hermes virtualenv. If Docker returns local fallback text instead of a generated description, use the native `./run-dashboard.sh` launcher or build an image that installs the matching Hermes runtime dependencies.

File and todo descriptions remain available in Docker because they are generated locally in the browser.

## Verify the Feature

Start the dashboard and run a terminal or code tool from chat. The card should:

1. Render immediately with an analyzing message.
2. Replace that message with a short intent description.
3. Keep the complete command or code in the expanded details.

You can also test the backend directly. This request consumes Codex usage:

```sh
DASHBOARD_URL="http://127.0.0.1:8081"
curl --fail-with-body \
  -H "Origin: $DASHBOARD_URL" \
  -H 'Content-Type: application/json' \
  --data '{"tool":"terminal","arguments":{"command":"git status --short"}}' \
  "$DASHBOARD_URL/api/tool-intent"
```

A successful response is a short plain-text sentence. An empty `204` response means the dashboard deliberately fell back without interrupting the tool card.

## Usage And Privacy

- Each `terminal` or `execute_code` call can make one Codex request.
- File and todo descriptions make no model request.
- Tool arguments are redacted with Hermes' forced credential redactor before transmission.
- OAuth credentials stay in the backend process and are never returned to the browser.
- Description calls consume the Codex account's normal usage allowance.
- Description tokens are not currently included in the dashboard's token-usage totals.

The endpoint follows the dashboard's existing network trust boundary. It requires a matching browser origin and applies process limits, but it is not a replacement for authentication in front of a remotely exposed dashboard. Keep the dashboard bound to localhost or place it behind access control you trust.

## Troubleshooting

### The card stays on local fallback text

Check that:

- `HERMES_HOME` points to the home containing the Codex OAuth login
- `HERMES_AGENT_PATH` points to the matching Hermes source or install tree
- the dashboard is running with the Hermes virtualenv
- `gpt-5.6-luna` is available to the authenticated account
- the dashboard has not reached its concurrency or rate limit

Run `hermes auth add openai-codex` only when Hermes reports that reauthentication is required. Do not delete or manually edit the auth store as a troubleshooting step.

### The direct request returns `403`

The `Origin` header must match the dashboard URL, including scheme, host, and port. Reverse proxies must also preserve `Host` and set the correct `X-Forwarded-Proto` value.

### The direct request returns `204`

The description is optional and failures are intentionally silent in the UI. Common causes are missing Hermes dependencies, unavailable Codex authentication, an unavailable Luna model, timeout, concurrency pressure, or rate limiting.

### The browser still shows the old header

Restart the dashboard after updating, then use **Dashboard Settings > Reload Dashboard** to clear cached static assets.
