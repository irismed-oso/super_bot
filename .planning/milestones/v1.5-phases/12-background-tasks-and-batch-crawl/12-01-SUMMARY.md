---
phase: 12-background-tasks-and-batch-crawl
plan: 01
subsystem: api
tags: [prefect, asyncio, httpx, slack, background-tasks, batch-processing]

# Dependency graph
requires:
  - phase: 11-fast-path-crawl-and-status
    provides: "Single-location crawl pattern, LOCATION_ALIASES, prefect_api module"
provides:
  - "Batch crawl command triggering all 23 EyeMed locations in parallel"
  - "Background monitor posting Slack progress updates every 2.5 minutes"
  - "get_flow_run_status() for polling individual Prefect flow run states"
  - "trigger_batch_crawl() for efficient batch deployment triggering with shared HTTP client"
affects: [13-error-ux]

# Tech tracking
tech-stack:
  added: []
  patterns: ["asyncio.create_task for fire-and-forget background monitoring", "shared httpx.AsyncClient for batch API calls"]

key-files:
  created: ["bot/background_monitor.py"]
  modified: ["bot/prefect_api.py", "bot/fast_commands.py", "bot/handlers.py"]

key-decisions:
  - "Single shared httpx.AsyncClient for all batch Prefect API calls (avoids 46+ separate client instantiations)"
  - "asyncio.create_task monitor runs in bot event loop without touching agent queue"
  - "Poll every 30s, post Slack updates every 2.5 minutes to avoid noise"

patterns-established:
  - "Background task pattern: asyncio.create_task with done_callback for error logging"
  - "slack_context dict passed through fast-command chain for background task spawning"

requirements-completed: [FAST-03, BGTK-01, BGTK-02, BGTK-03, BGTK-04]

# Metrics
duration: 3min
completed: 2026-03-24
---

# Phase 12 Plan 01: Background Tasks and Batch Crawl Summary

**Batch EyeMed crawl across all 23 locations with parallel Prefect triggers and asyncio background monitor posting Slack progress updates**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-24T18:41:28Z
- **Completed:** 2026-03-24T18:44:14Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Batch crawl command ("crawl all sites for 03.20") triggers all 23 locations in parallel using a single shared httpx client
- Background monitor polls Prefect every 30s and posts Slack thread updates every 2.5 minutes with completion/running/failed counts
- Final summary message groups locations by outcome when all runs are terminal
- 1-hour safety timeout prevents infinite polling; individual poll errors don't crash the monitor

## Task Commits

Each task was committed atomically:

1. **Task 1: Batch crawl trigger with parallel Prefect API calls** - `9279120` (feat)
2. **Task 2: Background monitor with progress polling and final summary** - `c9bef7e` (feat)

## Files Created/Modified
- `bot/prefect_api.py` - Added get_flow_run_status(), trigger_batch_crawl() with shared client
- `bot/fast_commands.py` - Added _BATCH_CRAWL_RE, _handle_batch_crawl, slack_context parameter threading
- `bot/background_monitor.py` - New module: start_batch_monitor, _monitor_loop, progress/summary formatters
- `bot/handlers.py` - Passes client/channel/thread_ts as slack_context to try_fast_command

## Decisions Made
- Used a single shared httpx.AsyncClient inside trigger_batch_crawl() instead of creating 46+ separate clients (one per find_deployment_id + create_flow_run call)
- Background monitor uses asyncio.create_task in the bot's event loop rather than a separate thread or process, keeping it simple and non-blocking without touching the agent queue
- Poll interval (30s) is separate from update interval (150s) to catch state changes quickly while avoiding Slack noise

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Batch crawl and background monitoring ready for production use
- Phase 13 (Error UX) can build on the status polling infrastructure added here

## Self-Check: PASSED

All files found, all commits verified.

---
*Phase: 12-background-tasks-and-batch-crawl*
*Completed: 2026-03-24*
