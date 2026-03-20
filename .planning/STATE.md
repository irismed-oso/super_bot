# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-18)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.
**Current focus:** Phase 3: End-to-End Integration — In Progress.

## Current Position

Phase: 3 of 4 (End-to-End Integration)
Plan: 4 of 5 in current phase (03-03 complete)
Status: Executing Phase 3
Last activity: 2026-03-20 — Completed 03-03-PLAN.md (Progress posting layer)

Progress: [██████████████████████░░░░░░░░] 60% (Phase 1-2 complete, Phase 3 plan 3/5)

## Performance Metrics

**Velocity:**
- Total plans completed: 8
- Average duration: ~3min
- Total execution time: ~22 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 1 | 4/4 | ~11min | ~3min |
| Phase 2 | 3/3 | ~9min | ~3min |
| Phase 3 | 1/5 | ~2min | ~2min |

**Recent Trend:**
- Last 5 plans: P04(5m), P2-01(2m), P2-02(2m), P2-03(5m), P3-03(2m)
- Trend: Stable

*Updated after each plan completion*
| Phase 01 P01 | 2min | 2 tasks | 4 files |
| Phase 01 P02 | 2min | 2 tasks | 6 files |
| Phase 01 P03 | 2min | 2 tasks | 5 files |
| Phase 01 P04 | 5min | 2 tasks | 3 files |
| Phase 02 P01 | 2min | 2 tasks | 3 files |
| Phase 02 P02 | 2min | 2 tasks | 3 files |
| Phase 02 P03 | 5min | 2 tasks | 1 files |
| Phase 03 P03 | 2min | 2 tasks | 2 files |
| Phase 03 P02 | 2min | 2 tasks | 3 files |

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
- [Phase 02-02]: Lazy queue initialization inside run_queue_loop() to avoid asyncio event loop issues at import time
- [Phase 02-02]: Hard-split fallback in split_long_message() for lines exceeding max_chars
- [Phase 02-03]: Test 3 max-turns partial pass accepted -- mechanism works but single-turn text prompts don't trigger multi-turn. Full validation deferred to Phase 3.
- [Phase 03-03]: Milestone detection uses ToolUseBlock.name matching against tool sets, not text parsing
- [Phase 03-03]: Dedup via nonlocal closure variable avoids class state for a single-use callback
- [Phase 03]: on_message callback added alongside on_text for backward compatibility with test harness
- [Phase 03]: is_code_task defaults True (worktrees are cheap); QueuedTask.cwd defaults None

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1: GCP-specific IAM bindings for Secret Manager access need to be validated against actual GCP project during planning — exact `roles/secretmanager.secretAccessor` assignment and `ExecStartPre` secret injection syntax unknown
- Phase 2: `claude-agent-sdk==0.1.49` streaming API `ResultMessage` field structure needs verification against live package before `bot/agent.py` is written
- Phase 3: GitLab-specific `glab` CLI command syntax for MR creation on the VM's bot user needs verification during planning

## Session Continuity

Last session: 2026-03-20
Stopped at: Completed 03-03-PLAN.md — Progress posting layer
Resume file: None
