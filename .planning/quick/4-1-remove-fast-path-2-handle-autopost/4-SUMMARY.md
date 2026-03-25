---
phase: quick-4
plan: 01
subsystem: bot
tags: [fast-commands, slack, cleanup, refactor]

requires:
  - phase: 22-sqlite-foundation-and-memory-commands
    provides: memory commands in fast_commands.py
provides:
  - Cleaned fast_commands.py with only memory + guard handlers
  - Agent pipeline now receives crawl, deploy status, bot status, autopost commands
affects: [agent-pipeline, eyemed-crawl, deploy]

tech-stack:
  added: []
  patterns: [fast-path-for-guards-only]

key-files:
  created: []
  modified:
    - bot/fast_commands.py
    - bot/handlers.py

key-decisions:
  - "Keep rollback guard alongside deploy guard (both block when agent task running)"
  - "Remove is_action_request entirely (was only needed for greedy fast-path)"

patterns-established:
  - "Fast-path reserved for instant-response commands only (memory CRUD, deploy/rollback guards)"

requirements-completed: [QUICK-4]

duration: 2min
completed: 2026-03-25
---

# Quick Task 4: Strip Fast Commands to Memory + Guards Only

**Removed 6 greedy fast-path handlers (crawl, deploy status/preview, eyemed status, bot status) so commands like "autopost eyemed" flow through to the agent pipeline**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-25T20:17:30Z
- **Completed:** 2026-03-25T20:19:18Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Stripped fast_commands.py from 740 lines to 273 lines (479 lines deleted)
- Removed all EyeMed crawl, deploy status/preview, bot status handlers and supporting infrastructure
- Removed LOCATION_ALIASES, _run_script, action-request detection, date parsing helpers
- FAST_COMMANDS registry reduced from 12 entries to 6 (4 memory + deploy guard + rollback guard)
- Removed is_action_request gate from try_fast_command

## Task Commits

Each task was committed atomically:

1. **Task 1: Strip fast_commands.py to memory + guards only** - `a8b27e1` (refactor)

## Files Created/Modified
- `bot/fast_commands.py` - Removed 6 handlers and all supporting code; kept memory commands and deploy/rollback guards
- `bot/handlers.py` - Updated fast-path comment to reflect reduced scope

## Decisions Made
- Kept rollback guard (exists in code at lines 382-406) alongside deploy guard -- both serve the same purpose of blocking during active agent tasks
- Removed is_action_request entirely rather than keeping it -- was only needed to prevent greedy fast-path from intercepting action messages

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Commands like "autopost eyemed", "crawl eyemed DME", "deploy status", "bot status" now flow through to agent pipeline
- Memory commands continue to work as fast-path instant responses
- Deploy/rollback guards continue to protect against concurrent operations

---
*Quick Task: 4*
*Completed: 2026-03-25*
