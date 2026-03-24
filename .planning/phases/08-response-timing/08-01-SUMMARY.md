---
phase: 08-response-timing
plan: 01
subsystem: ui
tags: [slack, formatting, elapsed-time]

# Dependency graph
requires:
  - phase: 04-progress-reporting
    provides: progress.post_result() and handlers.py result_cb
provides:
  - "Elapsed time footer on all Slack result messages (success, error, timeout)"
  - "_format_elapsed() utility for Xm Ys duration formatting"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["Italic footer appended before markdown conversion in post_result"]

key-files:
  created: []
  modified:
    - bot/progress.py
    - bot/handlers.py

key-decisions:
  - "Footer placed after PR URL but before markdown_to_mrkdwn conversion"
  - "Reuse duration_s variable in handlers.py instead of computing twice"

patterns-established:
  - "Elapsed time format: always Xm Ys with both minutes and seconds shown"

requirements-completed: [TMG-01, TMG-02]

# Metrics
duration: 1min
completed: 2026-03-24
---

# Phase 8 Plan 1: Response Timing Summary

**Elapsed time italic footer on all Slack replies using _format_elapsed() helper with Xm Ys format**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-24T04:54:48Z
- **Completed:** 2026-03-24T04:55:49Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added _format_elapsed() helper that converts seconds to "Xm Ys" format (always showing both units)
- Updated post_result() with optional duration_s parameter that appends italic footer
- Wired duration_s from handlers.py result_cb into post_result()
- Consolidated duplicate duration computation in handlers.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Add elapsed time footer to progress.py and wire from handlers.py** - `51322d8` (feat)

## Files Created/Modified
- `bot/progress.py` - Added _format_elapsed() and duration_s param to post_result() with success/error footer
- `bot/handlers.py` - Compute duration_s before post_result() and pass it; reuse for activity_log

## Decisions Made
- Footer placed after PR URL line but before markdown_to_mrkdwn conversion, so Slack italic formatting applies correctly
- Reused duration_s variable in handlers.py instead of computing time twice (was previously computed separately for activity_log)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Elapsed time footer is live on all result message types
- No blockers for future phases

---
*Phase: 08-response-timing*
*Completed: 2026-03-24*
