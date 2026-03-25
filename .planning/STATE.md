# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it -- writes code, runs scripts, debugs issues, deploys -- with full autonomy and persistent awareness.
**Current focus:** Milestone v1.8: Production Ops

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-25 - Completed quick task 2: create way to deploy super bot production via prefect

## Performance Metrics

**Velocity:**
- Total plans completed: 26
- Average duration: --
- Total execution time: --

## Accumulated Context

### Decisions

- v1.2: mic-transformer MCP server runs locally on VM as stdio subprocess
- v1.2: Direct MCP wiring (not Flask bridge) -- simpler, standard pattern
- v1.5: Fast-path single crawl (Phase 11) before batch/background (Phase 12)
- v1.5: asyncio.create_task monitor in bot event loop, no agent queue involvement
- v1.6: finish() edits progress message to show completion time; stop() silently cancels for error paths
- v1.6: Heartbeat timer 60s first tick then 180s intervals
- v1.7: Deploy script before live verification -- must deploy before you can verify
- v1.7: Reusable deploy script (no hardcoded versions) so future milestones use the same script

### Pending Todos

None yet.

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | extend run time timeout to 30 min | 2026-03-24 | 34a4444 | [1-extend-run-time-timeout-to-30-min](./quick/1-extend-run-time-timeout-to-30-min/) |
| 2 | create Prefect deploy pipeline for SuperBot | 2026-03-25 | 08fa13f | [2-create-way-to-deploy-super-bot-productio](./quick/2-create-way-to-deploy-super-bot-productio/) |

## Session Continuity

Last session: 2026-03-25
Stopped at: Completed quick task 2 -- Prefect deploy pipeline
Resume file: None
