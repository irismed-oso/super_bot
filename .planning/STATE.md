# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-24)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it -- writes code, runs scripts, debugs issues, deploys -- with full autonomy and persistent awareness.
**Current focus:** Phase 09 - Git Activity Logging (v1.4)

## Current Position

Phase: 09 of 13 (Git Activity Logging)
Plan: 1 of 1 in current phase (complete)
Status: Phase 09 complete
Last activity: 2026-03-24 -- Completed 09-01-PLAN.md (git activity capture)

Progress: [===================.] ~92% (phases 1-9, 11 complete; phase 10, 12-13 pending)

## Performance Metrics

**Velocity:**
- Total plans completed: 21
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
- v1.4: Post-session git log parsing (not real-time stream) for commit/PR capture simplicity
- v1.4: Deduplication via existing JSONL entries for same thread_ts + commit hash

### Pending Todos

None yet.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-03-24
Stopped at: Completed 09-01-PLAN.md (git activity capture)
Resume file: None
