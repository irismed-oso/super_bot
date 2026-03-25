# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it -- writes code, runs scripts, debugs issues, deploys -- with full autonomy and persistent awareness.
**Current focus:** Phase 22: SQLite Foundation and Memory Commands (v1.9)

## Current Position

Phase: 22-sqlite-foundation-and-memory-commands
Plan: 01 of 02 complete
Status: Executing phase 22
Last activity: 2026-03-25 - Completed 22-01: SQLite foundation and memory store

Progress: [==================..] 88% (phases 1-21 scoped, 16 complete; phase 22 in progress)

## Performance Metrics

**Velocity:**
- Total plans completed: 29
- Average duration: --
- Total execution time: --

## Accumulated Context

### Decisions

- v1.9: FTS5 MATCH with LIKE fallback for resilient search on malformed queries
- v1.9: porter unicode61 tokenizer for stemmed multilingual FTS
- v1.9: SQLite + FTS5 over vector DB (2 GB RAM constraint, sub-1K memory scale)
- v1.9: Single aiosqlite connection with WAL mode (prevents database locked errors)
- v1.9: Memory commands as fast-path (before existing patterns to avoid regex collisions)
- v1.9: Auto-recall capped at 5-8 memories with rules always included
- v1.9: Thread scanning as asyncio.create_task (does not block queue)
- v1.9: Conservative extraction only (explicit directives, not speculative statements)
- v1.8: Deploy commands handled outside agent queue (super_bot dies, mic_transformer polls directly)
- v1.8: Fast-path commands integrated into handlers.py _run_agent_real before agent queue dispatch

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

## Session Continuity

Last session: 2026-03-25
Stopped at: Completed 22-01-PLAN.md (SQLite foundation and memory store)
Resume file: None
