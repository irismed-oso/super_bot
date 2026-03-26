---
phase: 21-pipeline-status
plan: 01
subsystem: cli
tags: [prefect, pipeline, flow-runs, monitoring]

requires:
  - phase: 19-log-access
    provides: CLI pattern (log_tools.py) and Prefect API constants
provides:
  - Pipeline status CLI tool (python -m bot.pipeline_status)
  - Agent rule for pipeline status queries
affects: [agent-rules, prefect-monitoring]

tech-stack:
  added: []
  patterns: [CLI module with argparse and async fetch, status grouping]

key-files:
  created: [bot/pipeline_status.py]
  modified: [bot/handlers.py]

key-decisions:
  - "Agent pipeline (not fast-path) for pipeline status -- agent handles natural language time windows"
  - "Group FAILED/CRASHED first, then RUNNING/PENDING/SCHEDULED, then COMPLETED"
  - "Cap output at 2500 chars with completed run truncation for Slack safety"

patterns-established:
  - "Status grouping pattern: categorize API results by state, show failures first"

requirements-completed: [HLTH-02]

duration: 2min
completed: 2026-03-26
---

# Phase 21 Plan 01: Pipeline Status Summary

**Prefect flow run status CLI with grouped display (failed/running/completed) and agent rule for natural language queries**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-26T03:12:39Z
- **Completed:** 2026-03-26T03:14:35Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Pipeline status CLI queries Prefect API and groups flow runs by state
- Failed runs shown first with error details, then running, then completed (capped at 10)
- Agent rule added so the agent knows to use the CLI for pipeline status queries

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pipeline_status.py CLI module** - `b01c69b` (feat)
2. **Task 2: Add agent rules hint for pipeline status command** - `1a31bec` (feat)

## Files Created/Modified
- `bot/pipeline_status.py` - Prefect flow run query, grouping, formatting, and CLI entry point
- `bot/handlers.py` - Added agent rule for pipeline status queries

## Decisions Made
- Agent pipeline (not fast-path) for pipeline status -- agent handles natural language time windows
- Group FAILED/CRASHED first, then RUNNING/PENDING/SCHEDULED, then COMPLETED
- Cap output at 2500 chars with completed run truncation for Slack safety
- Show up to 10 completed runs then summarize remainder

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pipeline status tool ready for use via agent
- Nicole can ask "pipeline status" and the agent will run the CLI tool
- Follow-up with "prefect logs [run-name]" works via existing log_tools

---
*Phase: 21-pipeline-status*
*Completed: 2026-03-26*
