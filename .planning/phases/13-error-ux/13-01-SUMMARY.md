---
phase: 13-error-ux
plan: 01
subsystem: ux
tags: [slack, error-handling, fast-path, status-query]

# Dependency graph
requires:
  - phase: 11-fast-path
    provides: "FAST_COMMANDS registry, LOCATION_ALIASES dict, try_fast_command infrastructure"
  - phase: 12-batch-crawl
    provides: "background_monitor module with start_batch_monitor"
provides:
  - "Contextual error messages with task name, visual distinction, next-action suggestions"
  - "Fast-path bot status query handler for 'are you broken?' style messages"
  - "Public get_active_monitors() accessor on background_monitor"
  - "clean_text field on QueuedTask for threading user message through pipeline"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy import in _timeout_suggestion to avoid circular dependency between progress and fast_commands"
    - "Active monitor tracking via module-level list with done-callback cleanup"

key-files:
  created: []
  modified:
    - bot/progress.py
    - bot/handlers.py
    - bot/queue_manager.py
    - bot/fast_commands.py
    - bot/background_monitor.py

key-decisions:
  - "Slack emoji syntax (:hourglass: etc.) not Unicode -- formatter passes through correctly"
  - "Bot status handler placed last in FAST_COMMANDS to avoid false-matching eyemed commands"
  - "Lazy import of LOCATION_ALIASES in _timeout_suggestion to avoid circular import"

patterns-established:
  - "Error messages use emoji prefix + bold title + 'Was running:' line for consistent structure"
  - "Background task state exposed via get_active_monitors() for cross-module queries"

requirements-completed: [ERUX-01, ERUX-02, ERUX-03]

# Metrics
duration: 2min
completed: 2026-03-24
---

# Phase 13 Plan 01: Error UX Summary

**Contextual error messages with task name/next-action and fast-path "are you broken?" status handler**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-24T19:42:47Z
- **Completed:** 2026-03-24T19:44:55Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Timeout, failure, and cancelled messages now have distinct emoji prefixes for at-a-glance recognition
- Timeout messages name the task and suggest checking eyemed status for known locations
- "are you broken?", "are you still going?", "you ok?" etc. resolve via fast-path in seconds, not via agent session

## Task Commits

Each task was committed atomically:

1. **Task 1: Contextual error messages with visual distinction and next-action suggestions** - `a40fb4c` (feat)
2. **Task 2: Fast-path status query for "are you broken?" and similar messages** - `6e054e7` (feat)

## Files Created/Modified
- `bot/progress.py` - Contextual _format_error with three distinct styles and _timeout_suggestion helper
- `bot/handlers.py` - Threads clean_text through QueuedTask into result dict for error formatting
- `bot/queue_manager.py` - Added clean_text field to QueuedTask dataclass
- `bot/fast_commands.py` - _BOT_STATUS_RE regex and _handle_bot_status handler returning idle/running/background state
- `bot/background_monitor.py` - _active_monitors tracking list and get_active_monitors() public accessor

## Decisions Made
- Used Slack emoji syntax (:hourglass:, :no_entry_sign:, :x:) not Unicode -- formatter passes these through correctly
- Bot status handler placed last in FAST_COMMANDS so eyemed-specific commands match first
- Used lazy import of LOCATION_ALIASES inside _timeout_suggestion to avoid circular import between progress.py and fast_commands.py

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 13 is the final phase in v1.5 milestone -- all fast-path phases (11-13) complete
- Error UX improvements are ready for production deployment

---
*Phase: 13-error-ux*
*Completed: 2026-03-24*
