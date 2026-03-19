# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-18)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.
**Current focus:** Phase 2: Agent SDK Standalone — Plan 01 complete, Plan 02 next

## Current Position

Phase: 2 of 4 (Agent SDK Standalone)
Plan: 1 of 3 in current phase (02-01 complete)
Status: Executing Phase 2
Last activity: 2026-03-19 — Completed 02-01-PLAN.md (agent SDK core)

Progress: [█████████████░░░░░░░] 35% (Phase 1 complete, Phase 2: 1/3 plans done)

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: ~3min
- Total execution time: ~13 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 1 | 4/4 | ~11min | ~3min |
| Phase 2 | 1/3 | ~2min | ~2min |

**Recent Trend:**
- Last 5 plans: P01(2m), P02(2m), P03(2m), P04(5m), P2-01(2m)
- Trend: Stable

*Updated after each plan completion*
| Phase 01 P01 | 2min | 2 tasks | 4 files |
| Phase 01 P02 | 2min | 2 tasks | 6 files |
| Phase 01 P03 | 2min | 2 tasks | 5 files |
| Phase 01 P04 | 5min | 2 tasks | 3 files |
| Phase 02 P01 | 2min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Claude Agent SDK (not raw subprocess) — avoids documented TTY-hang bug; async-only, required for lazy listener pattern
- Roadmap: Socket Mode (no public URL) — eliminates need for load balancer, TLS, or ingress on the VM
- Roadmap: Phase 2 agent standalone before Phase 3 integration — debugging agent failures through Slack is significantly harder
- [Phase 01]: Config reads env at import time with empty defaults -- no crash on missing vars for local dev
- [Phase 01]: Deduplication uses threading.Lock (not asyncio.Lock) because TTLCache is sync-only
- [Phase 01-01]: Local Terraform state (no remote backend) -- operator can migrate later
- [Phase 01-01]: uv for Python package management; systemd enabled but not started until .env populated
- [Phase 01-03]: Lazy listener pattern with guard chain ordering: bot filter -> dedup -> access control -> channel filter
- [Phase 01-03]: register(app) pattern avoids circular imports between app.py and handlers.py
- [Phase 01-04]: Renamed /status to /sb-status because Slack reserves /status as a built-in command
- [Phase 01-04]: Deferred repo clone and systemd install in startup.sh until after credentials populated
- [Phase 01-04]: uv installed system-wide (/usr/local/bin) instead of root-only cargo path
- [Phase 02-01]: Atomic JSON writes via tempfile + os.replace() for session_map crash safety
- [Phase 02-01]: max_turns parameter on run_agent_with_timeout overrides module constant for test harness flexibility
- [Phase 02-01]: partial_texts list accumulated from AssistantMessage stream for timeout recovery

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1: GCP-specific IAM bindings for Secret Manager access need to be validated against actual GCP project during planning — exact `roles/secretmanager.secretAccessor` assignment and `ExecStartPre` secret injection syntax unknown
- Phase 2: `claude-agent-sdk==0.1.49` streaming API `ResultMessage` field structure needs verification against live package before `bot/agent.py` is written
- Phase 3: GitLab-specific `glab` CLI command syntax for MR creation on the VM's bot user needs verification during planning

## Session Continuity

Last session: 2026-03-19
Stopped at: Completed 02-01-PLAN.md — agent SDK core (session_map + agent wrapper)
Resume file: None
