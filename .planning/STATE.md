# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-18)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.
**Current focus:** Phase 1 — VM and Slack Bridge

## Current Position

Phase: 1 of 4 (VM and Slack Bridge)
Plan: 2 of 4 in current phase
Status: Executing
Last activity: 2026-03-19 — Completed 01-02-PLAN.md

Progress: [█░░░░░░░░░] 12%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 2min | 2 tasks | 4 files |
| Phase 01 P02 | 2min | 2 tasks | 6 files |

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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1: GCP-specific IAM bindings for Secret Manager access need to be validated against actual GCP project during planning — exact `roles/secretmanager.secretAccessor` assignment and `ExecStartPre` secret injection syntax unknown
- Phase 2: `claude-agent-sdk==0.1.49` streaming API `ResultMessage` field structure needs verification against live package before `bot/agent.py` is written
- Phase 3: GitLab-specific `glab` CLI command syntax for MR creation on the VM's bot user needs verification during planning

## Session Continuity

Last session: 2026-03-19
Stopped at: Completed 01-02-PLAN.md
Resume file: None
