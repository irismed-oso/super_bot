---
phase: 01-vm-and-slack-bridge
plan: 04
subsystem: infra
tags: [deployment, slack, gcp, systemd, terraform, runbook]

# Dependency graph
requires:
  - phase: 01-vm-and-slack-bridge/03
    provides: Bot Python package, systemd service unit, Slack manifest
provides:
  - DEPLOY.md step-by-step deployment runbook
  - Live deployed SuperBot in Slack workspace
  - Verified access control, dedup, slash commands in production
affects: [02-agent-sdk-standalone]

# Tech tracking
tech-stack:
  added: []
  patterns: [deployment-runbook-for-human-gated-steps]

key-files:
  created: [DEPLOY.md]
  modified: [terraform/main.tf, terraform/startup.sh]

key-decisions:
  - "Renamed /status to /sb-status because /status is a Slack reserved command keyword"
  - "Deferred repo clone and systemd service install in startup.sh until after credentials are populated"
  - "Switched GCP image to ubuntu-2404-lts-amd64 (actual image family name)"
  - "Install uv system-wide (/usr/local/bin) instead of root-only cargo path"

patterns-established:
  - "Human-gated deployment: DEPLOY.md runbook for steps Claude cannot automate (Slack app creation, Terraform apply, OAuth login, secret population)"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, SLCK-01, SLCK-02, SLCK-03, SLCK-04, SLCK-05, SLCK-06, SLCK-07, SLCK-08]

# Metrics
duration: 5min
completed: 2026-03-19
---

# Phase 1 Plan 04: Deployment Runbook and Live Verification Summary

**DEPLOY.md runbook guiding human operator through Slack app creation, Terraform apply, .env population, claude login, and service start -- verified live with all 8 tests passing**

## Performance

- **Duration:** 5 min (continuation after checkpoint approval)
- **Started:** 2026-03-19T00:00:00Z
- **Completed:** 2026-03-19T00:05:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created comprehensive DEPLOY.md with 9-step deployment runbook covering all human-gated operations
- Successfully deployed live SuperBot to GCP VM with systemd service running
- All 8 verification tests passed: authorized @mention response, unauthorized ignore, dedup, /sb-status, /cancel, /help, clean logs

## Task Commits

Each task was committed atomically:

1. **Task 1: Write deployment runbook (DEPLOY.md)** - `39038ba` (feat)
2. **Task 2: Deploy and verify live bot** - checkpoint:human-verify (approved)

**Deployment fixes during verification:**
- `a748d1d` (fix) - Rename /status to /sb-status -- Slack reserved keyword
- `778900f` (fix) - Update terraform for deployment -- image name, uv path, deferred clone

## Files Created/Modified
- `DEPLOY.md` - Step-by-step deployment runbook (9 steps: prerequisites through verification)
- `terraform/main.tf` - Fixed GCP image family to ubuntu-2404-lts-amd64
- `terraform/startup.sh` - Fixed uv install path, deferred clone until credentials exist

## Decisions Made
- Renamed /status to /sb-status because Slack reserves /status as a built-in command. This was discovered during live deployment when Slack rejected the slash command registration.
- Deferred repo clone and systemd service installation in startup.sh to after credential population, since the original script assumed credentials were available during VM bootstrap.
- Switched to system-wide uv installation (/usr/local/bin) because the root-only cargo path was not accessible to the bot user.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Renamed /status to /sb-status (Slack reserved keyword)**
- **Found during:** Task 2 (Deploy and verify live bot)
- **Issue:** Slack reserves /status as a built-in command; the bot's /status slash command could not be registered
- **Fix:** Renamed all three slash commands to /sb-status, /sb-cancel, /sb-help for namespace safety
- **Files modified:** bot/handlers.py, slack_manifest.yaml
- **Verification:** All three slash commands respond correctly in live Slack workspace
- **Committed in:** a748d1d (and prior commits bcd0f3d, 7e0dcbd for iterative fixes)

**2. [Rule 3 - Blocking] Fixed Terraform/startup.sh for actual deployment environment**
- **Found during:** Task 2 (Deploy and verify live bot)
- **Issue:** GCP image family name was wrong (ubuntu-2404-lts vs ubuntu-2404-lts-amd64), uv installed to root-only path, startup.sh tried to clone repo before credentials existed
- **Fix:** Corrected image name, installed uv system-wide, deferred clone and service install
- **Files modified:** terraform/main.tf, terraform/startup.sh
- **Verification:** VM bootstrapped successfully, service running
- **Committed in:** 778900f

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes were necessary for successful deployment. The /sb-status rename is a permanent naming convention. No scope creep.

## Issues Encountered
- Multiple iterations needed to get slash command naming right (first renamed all to /sb-*, then reverted /cancel and /help, then settled on all /sb-* prefixed). Final state: /sb-status, /sb-cancel, /sb-help.

## User Setup Required
None beyond what DEPLOY.md already covers -- the operator has completed all setup steps.

## Next Phase Readiness
- Phase 1 is fully complete: VM running, bot live, all access control and event handling verified
- Ready for Phase 2: Agent SDK Standalone -- the bot infrastructure is stable and accepting @mentions
- The bot currently responds with "Phase 1 -- agent not yet connected" placeholder; Phase 2 will replace this with real Claude Code sessions

---
*Phase: 01-vm-and-slack-bridge*
*Completed: 2026-03-19*
