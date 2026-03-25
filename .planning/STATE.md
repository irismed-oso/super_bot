# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it -- writes code, runs scripts, debugs issues, deploys -- with full autonomy and persistent awareness.
**Current focus:** Milestone v1.9: Persistent Memory

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-25 - Completed quick task 3: fast path is buggy. remove it

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
- v1.8: All ops commands implemented as fast-path handlers (no agent pipeline)
- v1.8: No new Python dependencies -- asyncio subprocess, httpx, resource module only
- v1.8: Self-deploy uses deploy-state file for post-restart confirmation
- v1.8: VRFY-01-04 folded into Phase 17 (verified during deploy workflow)

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | extend run time timeout to 30 min | 2026-03-24 | 34a4444 | [1-extend-run-time-timeout-to-30-min](./quick/1-extend-run-time-timeout-to-30-min/) |
| 2 | create Prefect deploy pipeline for SuperBot | 2026-03-25 | 08fa13f | [2-create-way-to-deploy-super-bot-productio](./quick/2-create-way-to-deploy-super-bot-productio/) |
| 3 | fast path is buggy. remove it | 2026-03-25 | d5fa074 | [3-fast-path-is-buggy-remove-it](./quick/3-fast-path-is-buggy-remove-it/) |

## Session Continuity

Last session: 2026-03-25
Stopped at: Milestone v1.9 started — defining requirements
Resume file: None
