# Self-Improvement / Autonomous Development Shipping Plan

## Task frame

Goal: make the Self-Improvement and Autonomous Development dashboard tabs safe to ship as first-class default-visible features without turning a dashboard view into an unexpected local mutation surface. Current posture remains hidden-by-default until the backend has explicit mutation gates, observe-only GET behavior, cron allowlists, and readiness checks.

## Vocabulary map

- **Self-improvement candidate:** proposed evidence-gated improvement item queued for selection/execution.
- **Self-improvement run:** execution cycle directory/projection under `SELF_IMPROVEMENT_HOME`.
- **Self-improvement event:** ledger row used to derive event coverage, repair hints, anomaly projections, and readiness state.
- **Autonomous pipeline:** registry entry containing specs and linked cron jobs that can be enabled/disabled together.
- **Cron job:** scheduled local job definition or trigger; enabling/running it mutates local scheduler state.
- **Readiness projection:** read-only status contract for local scripts, skills, Becomussy/outbox, stale locks, cron wiring, and legacy job risk.
- **Observe-only mode:** default UI/backend behavior where opening a tab performs only reads and disables mutation controls until explicit intent is supplied.
- **Mutation intent:** server-validated payload fields proving the user intended a specific state-changing operation; browser `confirm()` is not enough.

## Current backend routes

Self-improvement routes registered in `app.py`:

- `GET /api/self-improvement`
- `GET /api/self-improvement/runs`
- `GET /api/self-improvement/candidates`
- `POST /api/self-improvement/candidates`
- `POST /api/self-improvement/candidates/select`
- `POST /api/self-improvement/control`

Autonomous-development routes:

- `GET /api/autonomous-development`
- `POST /api/autonomous-development/pipelines`
- `PATCH /api/autonomous-development/pipelines/{pipeline_id}`
- `POST /api/autonomous-development/pipelines/{pipeline_id}/control`

Related cron routes with broader mutation power:

- `GET /api/cron`
- `POST /api/cron`
- `PATCH /api/cron/{job_id}`
- `DELETE /api/cron/{job_id}`
- `POST /api/cron/{job_id}/pause`
- `POST /api/cron/{job_id}/resume`
- `POST /api/cron/{job_id}/run`

## Current frontend controls

Self-Improvement panel controls:

- Refresh
- Pause Loop
- Resume Loop
- Kill-Switch
- Clear Stale Lock
- Add Evidence-Gated Candidate
- Select Next

Autonomous Development panel controls:

- Refresh
- Add Pipeline
- Enable Linked Jobs
- Disable Linked Jobs
- Edit Specs

Tabs are registered in nav/mobile nav and `DASHBOARD_TABS`, but currently excluded from `DEFAULT_VISIBLE_DASHBOARD_TABS`; `getDefaultHiddenDashboardTabs()` hides them for fresh browsers.

## Mutation surfaces

### Self-improvement

- Candidate creation writes `~/self-improvement/feature-candidates.jsonl` or delegates to `~/scripts/self-augment/self_improvement_queue.py` when available.
- Candidate selection mutates queue candidate status.
- Control actions mutate `~/.hermes/cron/jobs.json` for pause/resume/kill and may delete `~/self-improvement/self-improvement.lock.json`.
- `_append_self_improvement_audit()` writes `~/self-improvement/control-audit.jsonl`.

### Autonomous development

- Current `GET /api/autonomous-development` can create/update `~/.hermes/autonomous-development/pipelines.json` when registry/defaults are missing.
- Pipeline create/update writes registry and audit files.
- Pipeline control writes cron jobs, pipeline registry, and audit log.

### Cron

General cron routes can create/update/delete/pause/resume/run jobs through Hermes API. These must not become implicit controls for default-visible experimental panels without an allowlist and explicit server-side intent checks.

## Required local scripts, skills, services, and files

Self-improvement artifacts:

- `SELF_IMPROVEMENT_HOME` (default `~/self-improvement`)
- `~/self-improvement/runs/*`
- `~/self-improvement/feature-candidates.jsonl`
- `~/self-improvement/feature-candidate-events.jsonl`
- `~/self-improvement/queue.json` legacy fallback
- `~/self-improvement/control-audit.jsonl`
- `~/self-improvement/self-improvement.lock.json`
- `~/self-improvement/becomussy-resume-packet.json`
- `~/self-improvement/becomussy-resume-packet.compact.json`

Hermes artifacts:

- `~/.hermes/cron/jobs.json`
- `~/.hermes/becomussy_outbox.jsonl`
- `~/.hermes/autonomous-development/pipelines.json`
- `~/.hermes/autonomous-development/audit.jsonl`

Optional helper scripts:

- `~/scripts/self-augment/self_improvement_queue.py`
- `~/scripts/self-augment/becomussy_resume_packet.py`
- `~/scripts/self-augment/becomussy_outbox.py`

Expected self-improvement cron jobs:

- `self-improvement-loop`
- `self-improvement-research-queue`
- `self-improvement-feature-tournament`

Legacy autonomous jobs that should remain disabled unless explicitly acknowledged:

- `autonomous-research`
- `autonomous-build`
- `tournament-build`
- `project-curation-tournament`

Required/self-improvement-related skills currently checked by backend:

- `self-aug-decision-packet`
- `self-gap-scout`
- `self-tool-registry`
- `self-tool-hygiene`
- `self-tool-smoke`
- `hermes-agent`
- `becomussy`
- `systematic-debugging`

Banned or legacy skills checked by backend:

- `zai-web-search`
- `spec-driven-build`
- `tournament-build`
- `github-repo-management`

External/live services implied:

- Hermes API for cron proxy routes.
- Becomussy continuity/outbox replay ecosystem.
- Local cron runner consuming `~/.hermes/cron/jobs.json`.
- Local self-augment scripts under `~/scripts/self-augment`.

## Safety gaps before default-visible shipping

1. **GET is not fully observe-only:** autonomous-development GET currently may write the pipeline registry on fresh installs.
2. **Mutating routes lack explicit intent fields:** resume/select/clear stale lock/kill-switch and autonomous create/edit/enable/disable need action-specific server-side validation.
3. **Cron operations need allowlists:** custom pipeline `job_names` must not enable arbitrary local jobs.
4. **Frontend controls become powerful when visible:** mutation controls should be disabled/collapsed by default even when the tab is visible.
5. **Fresh-install readiness is incomplete:** missing scripts/skills/files should render graceful readiness items without writing local state.
6. **Kill-switch labeling is misleading:** current action pauses future cron state; it does not necessarily terminate live processes.
7. **Existing tests do not prove unsafe POSTs are rejected:** current coverage exercises happy paths and some confirmations, but not the required intent schema.

## Tests to add

### Backend mutation gate tests

- `POST /api/self-improvement/control` rejects `resume`, `kill`, and `clear_stale_lock` unless payload includes action-specific intent fields and acknowledgements.
- `POST /api/self-improvement/candidates/select` rejects empty body and requires `intent: "self_improvement_select_candidate"` plus observe-only override/acknowledgement.
- `POST /api/self-improvement/candidates` rejects candidate creation without `intent: "self_improvement_create_candidate"` and evidence fields.
- `POST /api/autonomous-development/pipelines` rejects create without `intent: "autonomous_pipeline_create"` and registry-write acknowledgement.
- `PATCH /api/autonomous-development/pipelines/{id}` rejects edit without `intent: "autonomous_pipeline_edit"` and registry-write acknowledgement.
- `POST /api/autonomous-development/pipelines/{id}/control` rejects enable/disable without `intent: "autonomous_pipeline_control"`, matching requested action, cron-write acknowledgement, and a stronger enable confirmation phrase.

### Cron allowlist tests

- Enabling/disabling pipelines only touches allowlisted jobs such as `self-improvement-loop`, `self-improvement-research-queue`, and `self-improvement-feature-tournament`.
- Arbitrary job names like `backup-secrets`, `deploy-prod`, or `random-job` are rejected.
- Legacy autonomous job enablement requires a separate explicit legacy override.

### Fresh-install GET tests

- With temp/empty `HERMES_HOME` and `SELF_IMPROVEMENT_HOME`, `GET /api/self-improvement` returns 200, writes no files, and reports missing readiness items.
- With temp/empty `HERMES_HOME`, `GET /api/autonomous-development` returns 200, does not create `pipelines.json`, and returns virtual/default pipeline suggestions or `registry_exists: false`.

### Readiness contract tests

Assert readiness reports:

- script existence for self-improvement queue, resume packet, and outbox helpers
- required/missing skills
- Becomussy/outbox preflight status
- stale lock existence/age/staleness
- self-improvement cron jobs present/enabled
- active legacy job count
- `observe_only: true` by default

### Frontend/static tests

- Mutation controls render disabled/hidden unless observe-only mode is explicitly disabled.
- Fetch payloads include required intent fields.
- Labels distinguish read-only status from mutating cron/file operations.
- Tabs are added to default-visible set only after these gates land.

## Phased plan

### Phase 0 — Document current state

Keep tabs hidden by default. Treat panels as powerful local-maintainer tooling until safety gates ship.

### Phase 1 — Make GET endpoints observe-only

Split autonomous registry loading into read-only projection and explicit initialize/write paths. Audit self-improvement GET helpers for hidden writes. Add fresh-install no-write tests.

### Phase 2 — Add backend mutation gates

Add shared explicit-intent validation and require action-specific fields on self-improvement resume/select/clear stale lock/kill-switch and autonomous create/edit/enable/disable. Unsafe POSTs must fail with 400/403.

### Phase 3 — Add cron allowlist

Centralize allowed job names for dashboard autonomous controls. Keep legacy jobs disabled unless explicitly acknowledged through a separate override.

### Phase 4 — Add readiness contract

Extend GET payloads or add readiness endpoints covering scripts, skills, Becomussy/outbox, stale locks, cron wiring, legacy jobs, registry presence, and observe-only mode.

### Phase 5 — Frontend observe-only default

Render status/readiness/ledger first. Collapse mutation controls behind a per-session enablement affordance and send backend-required intent fields. Rename ambiguous controls: `Resume Loop` → `Resume Cron Loop`; `Kill-Switch` → `Pause Future Runs / Request Kill-Switch`; `Clear Stale Lock` → `Clear Stale Lock File`; `Enable Linked Jobs` → `Enable Allowlisted Linked Cron Jobs`.

### Phase 6 — Default-visible release

Add `self-improvement` and `autonomous-development` to `DEFAULT_VISIBLE_DASHBOARD_TABS` only after first-open performs reads only and all mutation operations require explicit server-side intent.

### Phase 7 — Post-release hardening

Audit entries should include actor, intent, action, touched files/jobs, and readiness snapshot. Consider CSRF/nonce and an environment flag such as `DASHBOARD_ENABLE_AUTONOMOUS_MUTATIONS=1`, default false.

## Drift audit

- Restored read-only repair/anomaly parity for event coverage in the refactor copy: `_bounded_candidate_event_repair_hint`, `repair_hint`, `event_coverage_repair_hint`, `Repair Readiness`, `Anomaly Samples`, and inert `Next repair commands` UI are present and test-covered.
- This does **not** make Self-Improvement or Autonomous Development default-visible; mutation controls still require the remaining server-side intent/allowlist/readiness phases before default-visible shipping.
