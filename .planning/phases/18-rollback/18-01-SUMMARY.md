---
phase: 18-rollback
plan: 01
subsystem: infra
tags: [rollback, prefect, slack-bot, deploy, health-check]

# Dependency graph
requires:
  - phase: 17-deploy-foundation
    provides: deploy_state.py (record_deploy, write_deploy_state, _git), deploy.py (Prefect polling pattern), prefect_api.py
provides:
  - bot/rollback.py with handle_rollback() for self-rollback and external rollback
  - Enhanced deploy_state.py with pre_sha tracking and action field
  - Rollback guard in fast_commands.py
  - Rollback command routing in handlers.py
  - Rollback recovery in app.py
affects: [deploy, rollback, app-startup]

# Tech tracking
tech-stack:
  added: []
  patterns: [auto-roll-forward on health check failure, self-rollback via Prefect with deploy-state recovery]

key-files:
  created:
    - bot/rollback.py
  modified:
    - bot/deploy_state.py
    - bot/fast_commands.py
    - bot/handlers.py
    - bot/app.py

key-decisions:
  - "Rollback reuses Prefect deploy pipeline with target SHA as branch parameter"
  - "Health check: systemctl is-active + journal error scan for services; Prefect COMPLETED state suffices for service-less repos"
  - "Auto-roll-forward triggers on any failure (health check, Prefect FAILED/CANCELLED/CRASHED, timeout)"

patterns-established:
  - "Auto-roll-forward: failed rollback automatically redeploys pre-rollback SHA, double failure reports manual intervention needed"
  - "Rollback guard mirrors deploy guard pattern (blocks when agent busy unless force specified)"

requirements-completed: [RLBK-01, RLBK-02]

# Metrics
duration: 8min
completed: 2026-03-25
---

# Phase 18 Plan 01: Rollback Summary

**Git-based rollback via Slack with auto-roll-forward on health check failure, supporting both self-rollback (super_bot) and external rollback (mic_transformer)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-25T20:10:31Z
- **Completed:** 2026-03-25T20:18:31Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created bot/rollback.py with handle_rollback(), _health_check(), and auto-roll-forward logic
- Enhanced deploy_state.py with pre_sha tracking in record_deploy() and action parameter in write_deploy_state()
- Added rollback guard in fast_commands.py and command routing in handlers.py
- Updated app.py recovery to distinguish rollback vs deploy and post appropriate message

## Task Commits

Each task was committed atomically:

1. **Task 1: Enhance deploy_state.py and create bot/rollback.py** - `5b77e74` (feat)
2. **Task 2: Wire rollback commands into fast_commands.py, handlers.py, and app.py** - `4c1d7b9` (feat)

## Files Created/Modified
- `bot/rollback.py` - Rollback execution logic with handle_rollback(), _health_check(), auto-roll-forward
- `bot/deploy_state.py` - Enhanced record_deploy() with pre_sha, write_deploy_state() with action parameter
- `bot/fast_commands.py` - Rollback guard handler blocking when agent is busy
- `bot/handlers.py` - Rollback command regex and routing to handle_rollback()
- `bot/app.py` - Post-restart recovery distinguishes rollback vs deploy messages

## Decisions Made
- Rollback reuses Prefect deploy pipeline by passing target SHA as "branch" parameter (deploy script does git checkout)
- Health check for service-less repos (mic_transformer) just trusts Prefect COMPLETED state
- Auto-roll-forward triggers on any failure path (health check, Prefect terminal failure, timeout)
- Self-rollback stores current SHA in deploy-state so recovery code knows where to roll forward if needed

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Rollback infrastructure complete, ready for production use
- Self-rollback (super_bot) and external rollback (mic_transformer) both wired
- Auto-roll-forward provides safety net for failed rollbacks

---
*Phase: 18-rollback*
*Completed: 2026-03-25*
