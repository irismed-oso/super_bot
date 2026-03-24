# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-24)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it -- writes code, runs scripts, debugs issues, deploys -- with full autonomy and persistent awareness.
**Current focus:** Phase 11 - Fast-Path Crawl and Status (v1.5: Nicole-Ready Operations)

## Current Position

Phase: 11 of 13 (Fast-Path Crawl and Status)
Plan: 1 of 1 in current phase (complete)
Status: Phase 11 complete
Last activity: 2026-03-24 -- Completed 11-01-PLAN.md (fast-path crawl and status)

Progress: [===================.] ~88% (phases 1-8, 11 complete; v1.4 and phases 12-13 pending)

## Performance Metrics

**Velocity:**
- Total plans completed: 20
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

### Pending Todos

None yet.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-03-24
Stopped at: Completed 11-01-PLAN.md (fast-path crawl and status)
Resume file: None
