# Project Research Summary

**Project:** SuperBot v1.8 Production Ops
**Domain:** Slack-integrated production operations (deploy, rollback, logs, health monitoring, pipeline status)
**Researched:** 2026-03-25
**Confidence:** HIGH

## Executive Summary

SuperBot v1.8 is a production operations milestone that gives a small engineering team the ability to deploy code, tail logs, roll back, check bot health, and monitor Prefect pipelines — all from Slack, without SSH. The key insight from research is that because the bot runs ON the same GCP VM as all target repos, every new feature can be built using the existing stack (`asyncio.create_subprocess_exec`, `httpx`, `task_state`, `fast_commands`) with zero new dependencies. The recommended approach is to implement all ops commands as fast-path handlers — deterministic shell-command sequences that bypass the Claude agent pipeline entirely, keeping costs low and response times under 5 seconds.

The highest-value features are deploy and rollback for `super_bot` and `mic_transformer` (the two repos on the same VM with defined deploy paths). Log access via `journalctl` and the enhanced health dashboard are lower complexity and can ship alongside or just after deploy. Pipeline status is a straightforward extension of the existing `prefect_api.py` client. All four features share a common architecture: regex handler in `fast_commands.py` -> new ops module -> subprocess or httpx call -> truncated, formatted Slack response.

The defining risk of this milestone is self-deploy: when SuperBot deploys itself, `systemctl restart superbot` kills the running process before it can post a success message to Slack. This must be solved architecturally in the first phase with a pre-restart message and a post-startup confirmation file. A secondary risk cluster covers regression during rollback (broken deps, incompatible env vars) and log output flooding Slack with raw structlog JSON. Both have well-documented mitigations in the research.

## Key Findings

### Recommended Stack

No new Python packages are required for v1.8. Every feature is achievable with the existing production stack. The bot is already on the VM alongside all target repos, so `gcloud compute ssh` is not needed — direct `asyncio.create_subprocess_exec` calls to `git`, `pip`, `systemctl`, and `journalctl` are simpler, faster, and already used in `git_activity.py`, `worktree.py`, and `fast_commands.py`. The one infrastructure change required is a one-time manual sudoers update on the VM granting the `bot` user passwordless `systemctl` and `journalctl` access.

See [STACK.md](STACK.md) for the full integration point details, code patterns, and alternatives considered.

**Core technologies:**
- `asyncio.create_subprocess_exec` — all deploy/rollback/log subprocess calls — already established pattern throughout codebase
- `httpx.AsyncClient` — Prefect API queries for pipeline status and flow run logs — already in `prefect_api.py`
- `resource.getrusage()` (stdlib) — memory metrics for health dashboard — no new dep needed
- `config.py` `DEPLOY_REPOS` dict — new centralized registry of repo paths, service names, venvs, branches

**What NOT to add:** `paramiko`/`fabric` (SSH not needed), `psutil` (overkill), `systemd-python` (native deps), `prefect` SDK (100+ transitive deps), new DB tables for deploy history (in-memory list is sufficient for a 2-person team).

### Expected Features

See [FEATURES.md](FEATURES.md) for full feature inventory with complexity estimates and dependency graph.

**Must have (table stakes):**
- Deploy `super_bot` from Slack — including self-deploy restart handling and post-restart confirmation
- Deploy `mic_transformer` from Slack — git pull + pip install
- Deploy status — current commit, branch, last deploy time, pending changes count
- Git-based rollback — with health check and auto-roll-forward on failure
- Journald log tail — last N lines with optional grep filter, output truncated and parsed
- Bot health dashboard — uptime, queue depth, error count, memory, current version
- Pipeline status fast-path — Prefect flow run summary for last 24 hours

**Should have (differentiators):**
- Automatic health verification after deploy — confirms Slack connectivity, not just `systemctl is-active`
- Post-restart "I'm back" confirmation for self-deploys via deploy-state file checked on startup
- Log output parsing — extract timestamp + level + event from structlog JSON, strip context noise
- Deploy diff preview — `git log origin/main..HEAD` to show pending changes before deploying
- Prefect flow log access by run ID — fast-path command for what already exists as MCP tool

**Defer:**
- Deploy `irismed-service` and `oso-fe-gsnap` — deploy paths on VM not yet defined
- Application log file tailing — verify journald covers everything first
- Error rate trending / alerting — daily digest already handles this use case
- Blue-green or approval-gated deploys — explicitly out of scope per PROJECT.md

### Architecture Approach

All v1.8 features follow the established fast-path pattern: `handlers.py` event routing -> `fast_commands.py` regex matching -> dedicated ops module -> subprocess or API call -> formatted Slack response. Four new modules are introduced with clean separation of concerns. Two existing modules are extended. The critical structural change is that ops commands must be checked BEFORE `is_action_request()` in the command routing logic to prevent "deploy super_bot" from routing to the full agent pipeline.

See [ARCHITECTURE.md](ARCHITECTURE.md) for full data flow diagrams, regex patterns, and anti-patterns.

**Major components:**
1. `bot/deploy_ops.py` (new) — deploy/rollback engine; runs git/pip/systemctl locally via subprocess; handles self-deploy with delayed restart and deploy-state file
2. `bot/log_reader.py` (new) — reads journald via subprocess and Prefect logs via API; mandatory truncation to 3000 chars and structlog JSON parsing
3. `bot/health_ops.py` (new) — assembles health dashboard from `task_state`, `queue_manager`, git version, and journald error count
4. `bot/pipeline_ops.py` (new) — queries `prefect_api.list_recent_flow_runs()` and formats a compact status summary
5. `bot/fast_commands.py` (modified) — new command entries for deploy, rollback, logs, health, pipeline
6. `bot/prefect_api.py` (modified) — add `list_recent_flow_runs()` and `get_flow_run_logs()` endpoints

### Critical Pitfalls

See [PITFALLS.md](PITFALLS.md) for the full pitfall inventory with phase assignments, warning signs, and recovery strategies.

1. **Self-deploy kills the bot before confirming success** — Post "Deploying now, I'll be back shortly" BEFORE triggering `systemctl restart`. Write a deploy-state file with channel, thread_ts, and pre-SHA. On startup, check for this file and post "Deploy complete" or "Deploy failed" to the saved thread, then delete the file.

2. **Deploy during an active agent session destroys in-progress work** — Before deploying `super_bot`, check `get_current_task()`. If a task is running, warn: "A task is in progress. Say 'deploy force' to proceed." Notify the interrupted thread when force-deploying.

3. **Fast-path regex collisions and `is_action_request()` routing** — New ops commands overlap with existing patterns and `is_action_request()` can intercept "deploy super_bot" and route it to the agent instead of fast-path. Use anchored prefix patterns and add a dedicated `try_ops_command()` check before the action filter. Test the full command matrix before deploying.

4. **Rollback to an incompatible commit with no recovery** — Record the pre-rollback SHA before any `git reset`. After checkout + `pip install` + restart, run the full health check. If it fails, automatically revert to the pre-rollback SHA. Never skip `pip install` on rollback.

5. **Log output floods Slack with raw structlog JSON** — Default to 15-20 lines. Parse structlog JSON to extract `{timestamp} [{level}] {event}` only. Cap output at 3000 chars. Use `files_upload_v2` for large outputs. Scrub lines containing secret patterns before posting.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Deploy Foundation
**Rationale:** Highest-value feature with no dependencies on other new modules. Architectural decisions made here — subprocess pattern, config registry, self-deploy handling, ops command routing fix — underpin all subsequent phases. The self-deploy problem must be designed before any deploy code is written, not retrofitted.
**Delivers:** `deploy super_bot` (with post-restart confirmation), `deploy mic_transformer`, deploy status command, `DEPLOY_REPOS` config registry, ops command routing fix before `is_action_request()`
**Addresses:** All FEATURES.md priority 1 deploy features
**Avoids:** Self-deploy confirmation loss (Pitfall 1), deploy during active session (Pitfall 2), regex collision and `is_action_request()` bypass (Pitfall 6), concurrent deploy race condition

### Phase 2: Rollback
**Rationale:** Natural follow-on to deploy — shares the same subprocess infrastructure and config registry from Phase 1. Rollback depends on having deploy working (same health-check mechanism). Scoped separately because it has its own pitfall cluster (incompatible deps, no auto-recovery) that requires distinct test coverage.
**Delivers:** Git-based rollback with health check, automatic roll-forward on failure, pre-rollback SHA tracking
**Uses:** `deploy_ops.py` from Phase 1, same `_run_cmd` helper, same config registry
**Avoids:** Rollback to incompatible commit (Pitfall 4)

### Phase 3: Log Access
**Rationale:** Can be built in parallel with Phase 2 — no dependency on rollback. The most-requested debugging tool after deploy. Purely additive: new module, new fast-path entries, no changes to existing logic beyond extending `prefect_api.py`.
**Delivers:** `log_reader.py` with journald tail, grep filter, structlog parsing, output truncation; Prefect flow log fast-path
**Uses:** `asyncio.create_subprocess_exec` (established), `prefect_api.py` extension for `get_flow_run_logs()`
**Avoids:** Log flood in Slack (Pitfall 5), secret leakage in log output

### Phase 4: Health Dashboard
**Rationale:** Lowest complexity — mostly assembles data from modules already built in Phases 1-3 (git version from deploy_ops, error count via journald from log_reader, uptime from task_state). Build last because existing `_handle_bot_status()` already answers "is the bot alive?" for immediate needs.
**Delivers:** `health_ops.py` with uptime, queue depth, error count, memory, current version, last restart, active monitors
**Addresses:** FEATURES.md priority 3 health features
**Avoids:** Shallow health check that only checks `systemctl is-active` without confirming Slack connectivity (Pitfall 7)

### Phase 5: Pipeline Status Fast-Path
**Rationale:** Straightforward extension of `prefect_api.py` with a new `list_recent_flow_runs()` endpoint. Naturally follows Phase 3 (both touch `prefect_api.py`). Existing agent-based pipeline investigation already works; this adds the fast-path summary layer for the common "how are the crawls doing?" query.
**Delivers:** `pipeline_ops.py` with 24h flow run summary; `prefect_api.list_recent_flow_runs()` endpoint
**Uses:** Existing `httpx.AsyncClient` Prefect auth pattern
**Avoids:** Prefect API pagination bug on large flow run history; tight-loop polling (cache results 30-60 seconds)

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** Rollback uses the same deploy engine. Building deploy first gives rollback a working foundation to reuse, and the self-deploy architectural decisions made in Phase 1 apply directly to rollback of `super_bot`.
- **Phase 3 parallel with Phase 2:** Log access has no dependency on rollback. Both can be planned concurrently; log access is independently testable and ships visible value immediately.
- **Phases 4-5 last:** Both are incremental additions to working functionality. The existing `_handle_bot_status()` covers the critical health question until Phase 4 ships. Phase 5 complements Phase 3's Prefect log access.
- **Ops command routing fix must happen in Phase 1:** The `is_action_request()` bypass affects all subsequent phases. Fix it once in Phase 1 and all later fast-path additions benefit automatically.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Deploy):** Self-deploy post-restart confirmation mechanism needs detailed design — deploy-state file format, startup hook location in `app.py`, failure path when new code crashes on startup. Also verify sudo permissions and service names on the production VM before coding begins.
- **Phase 2 (Rollback):** Auto-roll-forward logic needs careful sequencing. Verify `pip install` downgrade behavior for rollback across a major dependency change.

Phases with standard patterns (skip research-phase):
- **Phase 3 (Logs):** `journalctl` subprocess and structlog JSON parsing are well-understood. Output truncation pattern already exists in `formatter.py`. No novel integration surface.
- **Phase 4 (Health):** Entirely within existing module boundaries. `resource.getrusage()` is stdlib and well-documented. `task_state` and `queue_manager` APIs are already used.
- **Phase 5 (Pipeline):** `prefect_api.py` extension follows the established httpx pattern already in production. No new authentication or integration surface.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Directly verified against existing production codebase. No new deps means no version compatibility uncertainty. |
| Features | HIGH | Derived from direct codebase analysis and PROJECT.md design decisions. Feature scope is well-bounded for a 2-person team. |
| Architecture | HIGH | Component boundaries mirror existing fast-path patterns. All integration points verified in running production code. |
| Pitfalls | HIGH | Based on codebase analysis of actual failure modes, systemd SIGTERM behavior, Slack API constraints, and Prefect API documented limits. |

**Overall confidence:** HIGH

### Gaps to Address

- **`mic_transformer` systemd service status:** STACK.md shows `service: None` for mic_transformer but FEATURES.md references it as an "API server." Verify whether mic_transformer runs as a systemd service before Phase 1 coding. If it does have a service, the health check and restart steps in deploy are needed; if not, deploy is git pull + pip install only.
- **Sudoers state on production VM:** Research assumes passwordless sudo for `systemctl` and `journalctl` can be added. Verify the VM's current sudoers configuration before Phase 1 to avoid a blocker during implementation.
- **`oso-fe-gsnap` and `irismed-service` deploy paths:** Both repos are in the proposed config registry with `service: None` and unknown deploy workflows. Treat as deferred. Do not block v1.8 on defining these.
- **Startup hook for post-restart deploy confirmation:** The deploy-state file check needs a hook in `app.py` startup sequence. The exact insertion point needs verification during Phase 1 planning (before Socket Mode connect? after? in a startup task?).

## Sources

### Primary (HIGH confidence)
- `bot/fast_commands.py` — fast-path command pattern, `is_action_request()`, `_run_script` timeout, existing command registry
- `bot/prefect_api.py` — existing httpx Prefect API client and auth pattern
- `bot/background_monitor.py` — background task pattern, progress update approach for deploy
- `bot/task_state.py` — uptime, recent task tracking for health dashboard extension
- `bot/handlers.py` — event routing, dedup, access control, command dispatch flow
- `bot/queue_manager.py` — serial queue, current task state, `get_current_task()` for deploy guard
- `scripts/deploy.sh` — reference deploy sequence (push, pull, deps, restart, health check)
- `scripts/restart_superbot.sh` — manual restart pattern for recovery reference

### Secondary (MEDIUM confidence)
- Prefect REST API `/logs/filter` and `/flow_runs/filter` endpoints — verified from existing `prefect_api.py` usage patterns; full API reference at https://docs.prefect.io/latest/api-ref/rest-api-reference/
- Slack message size limits (~4000 chars) and `files_upload_v2` requirement — established Slack platform constraints (deprecated `files.upload` since 2024)
- systemd SIGTERM behavior on `systemctl restart` — standard Linux behavior; confirmed by existing `restart_superbot.sh` manual restart pattern

---
*Research completed: 2026-03-25*
*Ready for roadmap: yes*
