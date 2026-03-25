---
phase: 15-deploy-script
plan: 01
subsystem: infra
tags: [bash, gcloud, systemd, deploy, ssh]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: VM setup, superbot.service, gcloud SSH access
provides:
  - Reusable one-command deploy script (scripts/deploy.sh)
  - Updated DEPLOY.md with generic deploy workflow
affects: [16-live-verify, all future deployments]

# Tech tracking
tech-stack:
  added: []
  patterns: [reusable deploy script with flags, health check after restart]

key-files:
  created:
    - scripts/deploy.sh
  modified:
    - DEPLOY.md

key-decisions:
  - "Single reusable script replacing version-specific deploy scripts"
  - "Configurable flags (--skip-push, --skip-deps, --branch) for flexible deployment"

patterns-established:
  - "Deploy pattern: push, pull, deps, restart, health check with pass/fail exit codes"
  - "Variables at top of deploy script (VM, ZONE, BOT_USER, SERVICE, REPO_DIR) for easy configuration"

requirements-completed: [DPLY-01, DPLY-02]

# Metrics
duration: 8min
completed: 2026-03-25
---

# Phase 15 Plan 01: Deploy Script Summary

**Reusable deploy script replacing version-specific scripts with one-command push/pull/restart/health-check workflow**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-25
- **Completed:** 2026-03-25
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Created reusable `scripts/deploy.sh` with no hardcoded version numbers
- Script handles full deploy lifecycle: push, SSH pull, pip install, systemctl restart, health check
- Added `--skip-push`, `--skip-deps`, and `--branch` flags for flexible usage
- Updated DEPLOY.md with generic deploy section documenting the script
- Deployed to production VM successfully -- service active, no errors in logs

## Task Commits

Each task was committed atomically:

1. **Task 1: Create reusable deploy script** - `2dd5eeb` (feat)
2. **Task 2: Update DEPLOY.md with generic deploy section** - `dd0223e` (docs)
3. **Task 3: Deploy to VM and verify bot is live** - checkpoint:human-verify (approved, no commit needed)

## Files Created/Modified
- `scripts/deploy.sh` - Reusable deploy script with push/pull/deps/restart/health-check steps
- `DEPLOY.md` - Added "Deploying Updates (Any Milestone)" section with script usage

## Decisions Made
- Single reusable script with configurable flags instead of per-version scripts
- Variables at top of file for easy configuration across environments
- Health check examines last 20 journal lines for ERROR/Traceback indicators

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Deploy script proven working on production VM
- Ready for Phase 16 live verification -- bot is deployed and responding
- Future milestones can deploy with `bash scripts/deploy.sh`

## Self-Check: PASSED

- FOUND: scripts/deploy.sh
- FOUND: DEPLOY.md
- FOUND: 2dd5eeb (Task 1 commit)
- FOUND: dd0223e (Task 2 commit)

---
*Phase: 15-deploy-script*
*Completed: 2026-03-25*
