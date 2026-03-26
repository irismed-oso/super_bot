# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it -- writes code, runs scripts, debugs issues, deploys -- with full autonomy and persistent awareness.
**Current focus:** Phase 21: Pipeline Status (v1.4)

## Current Position

Phase: 21-pipeline-status
Plan: 01 of 01 complete
Status: Phase 21 complete
Last activity: 2026-03-26 - Completed 21-01: Pipeline status CLI and agent rule

Progress: [===================.] 96% (phases 1-21 scoped, 19 complete; phases 22-24, 20 complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 36
- Average duration: --
- Total execution time: --

## Accumulated Context

### Decisions

- v1.9: FTS5 MATCH with LIKE fallback for resilient search on malformed queries
- v1.9: porter unicode61 tokenizer for stemmed multilingual FTS
- v1.9: SQLite + FTS5 over vector DB (2 GB RAM constraint, sub-1K memory scale)
- v1.9: Single aiosqlite connection with WAL mode (prevents database locked errors)
- v1.9: Memory commands as fast-path (before existing patterns to avoid regex collisions)
- v1.9: Forget command uses search-then-confirm for multiple matches, direct delete for single/numeric ID
- v1.9: Auto-recall capped at 5-8 memories with rules always included
- v1.9: Recall block positioned between user text and AGENT_RULES in prompt hierarchy
- v1.9: Rules exempt from token budget truncation; extras truncated first
- v1.9: Thread scanning as asyncio.create_task (does not block queue)
- v1.9: Conservative extraction only (explicit directives, not speculative statements)
- v1.9: Lazy Anthropic client init with try/except ImportError for graceful degradation
- v1.9: Substring-based dedup for memory extraction (bidirectional containment check)
- v1.9: claude-sonnet-4-20250514 for extraction (fast, cheap, sufficient)
- v1.4: CLI entry point over MCP tool for log access (agent has bash, simpler wiring)
- v1.4: Truncation from beginning keeps most recent lines, 2800 char limit for Slack headroom
- v1.4: Conservative secret scrubbing (known patterns only, not aggressive heuristics)
- v1.8: Rollback reuses Prefect deploy pipeline with target SHA as branch parameter
- v1.8: Auto-roll-forward on any rollback failure (health check, Prefect failure, timeout)
- v1.8: Health check: systemctl + journal scan for services; Prefect COMPLETED suffices for service-less repos
- v1.8: Deploy commands handled outside agent queue (super_bot dies, mic_transformer polls directly)
- v1.8: Fast-path commands integrated into handlers.py _run_agent_real before agent queue dispatch
- v1.4: Agent pipeline (not fast-path) for pipeline status -- agent handles natural language time windows
- v1.4: Pipeline status groups FAILED/CRASHED first, then RUNNING, then COMPLETED with 2500 char cap

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 24 (Thread Scanning): Extraction prompt quality is the primary unknown -- no proven template exists; plan for shadow-mode validation before auto-storing

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | extend run time timeout to 30 min | 2026-03-24 | 34a4444 | [1-extend-run-time-timeout-to-30-min](./quick/1-extend-run-time-timeout-to-30-min/) |
| 2 | create Prefect deploy pipeline for SuperBot | 2026-03-25 | 08fa13f | [2-create-way-to-deploy-super-bot-productio](./quick/2-create-way-to-deploy-super-bot-productio/) |
| 3 | fast path is buggy. remove it | 2026-03-25 | d5fa074 | [3-fast-path-is-buggy-remove-it](./quick/3-fast-path-is-buggy-remove-it/) |
| 4 | strip fast-path to memory + guards only | 2026-03-25 | a8b27e1 | [4-1-remove-fast-path-2-handle-autopost](./quick/4-1-remove-fast-path-2-handle-autopost/) |
| Phase 20-health-dashboard P01 | 1min | 1 tasks | 1 files |
| Phase 21-pipeline-status P01 | 2min | 2 tasks | 2 files |

## Session Continuity

Last session: 2026-03-26
Stopped at: Completed 21-01-PLAN.md (pipeline status)
Resume file: None
