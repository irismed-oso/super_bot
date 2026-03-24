---
phase: 11-fast-path-crawl-and-status
plan: 01
subsystem: bot
tags: [prefect, regex, async, eyemed, crawl, status]

requires:
  - phase: 08-fast-path-and-response-timing
    provides: fast_commands.py pattern-match framework and try_fast_command wiring
provides:
  - Prefect API async client (bot/prefect_api.py) for deployment lookup and flow run creation
  - EyeMed crawl handler triggered by "crawl eyemed {location} {date}" pattern
  - Smart location extraction regex matching all 23 EyeMed locations anywhere in text
  - "today"/"now" date resolution in status queries
affects: [12-batch-crawl, 13-error-ux]

tech-stack:
  added: [requests]
  patterns: [asyncio.to_thread for sync HTTP in async handlers, dynamic regex from alias map]

key-files:
  created: [bot/prefect_api.py]
  modified: [bot/fast_commands.py]

key-decisions:
  - "Used asyncio.to_thread wrapping requests.post rather than aiohttp to keep dependency footprint small"
  - "Location aliases stored as flat dict with lowercase keys; multi-word locations get both hyphenated and spaced entries"
  - "Crawl entry placed before status in FAST_COMMANDS to prevent 'crawl eyemed DME' matching status regex"
  - "_DATE_RE updated to make year optional (MM.DD matches in addition to MM.DD.YY) with auto-append of current year"

patterns-established:
  - "Prefect API client pattern: asyncio.to_thread + requests.post with basic auth"
  - "Location alias map: single source of truth for location name normalization"

requirements-completed: [FAST-01, FAST-02, FAST-04]

duration: 2min
completed: 2026-03-24
---

# Phase 11 Plan 01: Fast-Path Crawl and Status Summary

**Prefect API client with EyeMed crawl trigger and smart location extraction for natural-language status queries**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-24T18:22:53Z
- **Completed:** 2026-03-24T18:25:05Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created async Prefect API client (find_deployment_id, create_flow_run) using asyncio.to_thread
- Added EyeMed crawl handler matching "crawl eyemed DME 03.20" and variants, triggering Prefect deployments
- Built LOCATION_ALIASES map for all 23 EyeMed locations with case-insensitive lookup
- Added dynamic _LOCATION_EXTRACT_RE that finds known location names anywhere in text (no prefix required)
- Added "to today" / "to now" date resolution in status handler
- Updated _DATE_RE to support dates without year (MM.DD auto-appends current year)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Prefect API client and EyeMed crawl handler** - `2065043` (feat)
2. **Task 2: Improve status location parsing** - included in `2065043` (structurally interleaved with Task 1 -- LOCATION_ALIASES and _LOCATION_EXTRACT_RE serve both crawl and status)

## Files Created/Modified
- `bot/prefect_api.py` - Async Prefect API client with find_deployment_id and create_flow_run
- `bot/fast_commands.py` - Added crawl handler, location aliases, smart location extraction, date normalization

## Decisions Made
- Used asyncio.to_thread wrapping requests.post rather than aiohttp to minimize new dependencies
- Location aliases stored as flat dict with lowercase keys; multi-word locations get both hyphenated and spaced entries
- Crawl entry placed before status in FAST_COMMANDS registry to prevent regex false matches
- _DATE_RE updated to make year portion optional, with _normalize_date auto-appending current 2-digit year

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing requests dependency**
- **Found during:** Task 1 verification
- **Issue:** requests library not installed in project venv (prefect_api.py imports it)
- **Fix:** pip install requests
- **Files modified:** none (runtime dependency)
- **Verification:** Import succeeds after install
- **Committed in:** n/a (pip install, not tracked in git)

**2. [Rule 2 - Missing Critical] Combined Task 1 and Task 2 into single commit**
- **Found during:** Task 1 implementation
- **Issue:** LOCATION_ALIASES and _LOCATION_EXTRACT_RE are shared between crawl (Task 1) and status (Task 2) handlers -- cannot be split without creating a broken intermediate state
- **Fix:** Implemented both tasks together in a single coherent write
- **Verification:** Both Task 1 and Task 2 verification scripts pass independently

---

**Total deviations:** 2 (1 blocking dependency, 1 structural merge)
**Impact on plan:** Both necessary for correctness. No scope creep.

## Issues Encountered
None beyond the missing requests dependency.

## User Setup Required
None - no external service configuration required. The requests library needs to be installed on the VM (`pip install requests` in the bot venv).

## Next Phase Readiness
- Prefect API client pattern established, ready for batch crawl (Phase 12)
- LOCATION_ALIASES available for reuse in error UX handlers (Phase 13)
- Fast command registry now has 2 entries (crawl + status)

---
*Phase: 11-fast-path-crawl-and-status*
*Completed: 2026-03-24*
