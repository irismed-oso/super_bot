---
phase: 17-deploy-foundation
plan: 02
subsystem: infra
tags: [deploy, prefect, slack-ops, asyncio, self-restart]

requires:
  - phase: 17-deploy-foundation
    provides: "REPO_CONFIG, resolve_repo(), deploy-state I/O, async git helpers, fast-path handlers"
provides:
  - "handle_deploy() for both self-deploy (super_bot) and external deploy (mic_transformer)"
  - "Post-restart recovery hook in app.py (_check_deploy_recovery)"
  - "Deploy command routing in handlers.py (fast-path + deploy dispatch)"
affects: [17-03-deploy-verification]

tech-stack:
  added: []
  patterns: ["self-deploy with deploy-state recovery", "Prefect-triggered deploy with polling", "edit-in-place deploy progress"]

key-files:
  created: [bot/deploy.py]
  modified: [bot/app.py, bot/handlers.py]

key-decisions:
  - "Deploy commands handled outside the agent queue (super_bot dies during deploy, mic_transformer polls directly)"
  - "Fast-path commands integrated into handlers.py _run_agent_real before agent queue dispatch"
  - "Post-restart recovery uses 5-second delay to wait for Socket Mode connection"

patterns-established:
  - "Self-deploy pattern: write deploy-state -> post pre-restart message -> trigger Prefect -> die -> recover on startup"
  - "External deploy pattern: trigger Prefect -> poll every 5s -> edit progress in-place -> report terminal state"

requirements-completed: [SDPL-01, SDPL-02]

duration: 4min
completed: 2026-03-25
---

# Phase 17 Plan 02: Deploy Execution Summary

**Prefect-triggered deploy handlers for super_bot (self-restart with state recovery) and mic_transformer (poll-and-report), wired into app.py startup and handlers.py dispatch**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-25T18:29:48Z
- **Completed:** 2026-03-25T18:33:43Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created bot/deploy.py with handle_deploy() supporting both self-deploy and external deploy flows
- Added post-restart deploy-state recovery hook in app.py that posts "I'm back" to the original thread
- Wired fast-path commands and deploy command routing into handlers.py before agent queue dispatch

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bot/deploy.py with Prefect-triggered deploy for both repos** - `ebe4e03` (feat)
2. **Task 2: Wire deploy recovery into app.py and deploy routing into handlers.py** - `1a9af89` (feat)

## Files Created/Modified
- `bot/deploy.py` - Deploy execution logic: handle_deploy(), _self_deploy(), _external_deploy(), polling loop
- `bot/app.py` - _check_deploy_recovery() and _delayed_deploy_check() for post-restart confirmation
- `bot/handlers.py` - Fast-path dispatch via try_fast_command(), deploy command routing via _DEPLOY_CMD_RE

## Decisions Made
- Deploy commands are handled outside the agent queue because super_bot will die during self-deploy and mic_transformer needs a direct polling loop
- Fast-path commands (deploy status, preview, guard) are checked in handlers.py before any agent queue logic, editing the ack message in-place
- Post-restart recovery uses asyncio.create_task with 5-second sleep before checking deploy-state, ensuring Socket Mode connection is established first

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- slack_bolt not available in local development venv (production-only dependency), so import verification used AST parsing instead of runtime imports. This is expected and not a concern.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Deploy execution is fully wired: fast-path for status/preview, direct dispatch for deploy commands
- Plan 03 (deploy verification) can now test the complete deploy workflow on the VM
- handlers.py has try_fast_command() integration that was noted as missing in Plan 01 summary

## Self-Check: PASSED

All files exist. All commits verified.

---
*Phase: 17-deploy-foundation*
*Completed: 2026-03-25*
