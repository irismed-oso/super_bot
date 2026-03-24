# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-24)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it -- writes code, runs scripts, debugs issues, deploys -- with full autonomy and persistent awareness.
**Current focus:** Milestone v1.6 Progress Heartbeat -- Phase 14

## Current Position

Phase: 14 of 14 (Progress Heartbeat)
Plan: 1 of 1 in current phase
Status: Phase complete
Last activity: 2026-03-24 -- Completed 14-01 progress heartbeat

## Performance Metrics

**Velocity:**
- Total plans completed: 25
- Average duration: --
- Total execution time: --

## Accumulated Context

### Decisions

- v1.2: mic-transformer MCP server runs locally on VM as stdio subprocess
- v1.2: Direct MCP wiring (not Flask bridge) -- simpler, standard pattern
- v1.2: Read-only tools before mutation tools -- validates credential pathways with zero blast radius
- v1.3: Elapsed time footer placed after PR URL but before markdown conversion
- v1.5: Fast-path phases numbered 11-13 (v1.4 already occupies 9-10)
- v1.5: Fast-path single crawl (Phase 11) before batch/background (Phase 12) -- single proves the Prefect API pattern before parallelizing it
- v1.5: Error UX (Phase 13) depends on Phase 11 (needs fast-path status query infrastructure for the "are you broken?" handler)
- v1.5: Used asyncio.to_thread wrapping requests.post for Prefect API (keeps dependency footprint small vs aiohttp)
- v1.5: LOCATION_ALIASES as flat dict with lowercase keys -- single source of truth for all 23 EyeMed locations
- v1.5: Crawl before status in FAST_COMMANDS registry to prevent regex false matches
- v1.5: Single shared httpx.AsyncClient for batch Prefect API calls (avoids 46+ separate clients)
- v1.5: asyncio.create_task monitor in bot event loop, no agent queue involvement
- v1.5: Poll every 30s, post Slack updates every 2.5 minutes to balance freshness vs noise
- v1.4: Post-session git log parsing (not real-time stream) for commit/PR capture simplicity
- v1.4: Deduplication via existing JSONL entries for same thread_ts + commit hash
- v1.5: Slack emoji syntax (:hourglass: etc.) not Unicode for error messages -- formatter passes through correctly
- v1.5: Bot status handler placed last in FAST_COMMANDS to avoid false-matching eyemed commands
- v1.5: Lazy import of LOCATION_ALIASES in _timeout_suggestion to avoid circular import
- [Phase 10]: Separate digest_changelog.py module for testability; cross-check is best-effort with graceful degradation
- v1.6: finish() edits progress message to show completion time; stop() silently cancels for error paths
- v1.6: Heartbeat timer 60s first tick then 180s intervals; milestone updates use full heartbeat format string

### Pending Todos

None yet.

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | extend run time timeout to 30 min | 2026-03-24 | 34a4444 | [1-extend-run-time-timeout-to-30-min](./quick/1-extend-run-time-timeout-to-30-min/) |

## Session Continuity

Last session: 2026-03-24
Stopped at: Completed 14-01-PLAN.md -- Phase 14 progress heartbeat complete
Resume file: None
