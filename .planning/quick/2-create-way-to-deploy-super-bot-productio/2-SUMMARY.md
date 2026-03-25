---
phase: quick
plan: 2
subsystem: infra
tags: [prefect, deploy, systemd, subprocess]

requires:
  - phase: none
    provides: N/A
provides:
  - Prefect-based deploy flow for SuperBot VM
  - Local trigger script for remote deploys without gcloud auth
affects: [deploy, infra]

tech-stack:
  added: [prefect flow.serve]
  patterns: [Prefect deployment via serve(), stdlib-only HTTP client for API triggers]

key-files:
  created:
    - prefect/deploy_superbot_flow.py
    - scripts/deploy_via_prefect.py
  modified:
    - DEPLOY.md

key-decisions:
  - "stdlib-only trigger script (urllib) to avoid dependency on venv"
  - "Prefect serve() model instead of work pool for simpler single-flow deployment"

patterns-established:
  - "Prefect flow.serve() for long-running deployment registrations on VM"

requirements-completed: []

duration: 2min
completed: 2026-03-25
---

# Quick Task 2: Deploy SuperBot via Prefect Summary

**Prefect deploy pipeline with VM-side flow (git pull, deps, restart, health check) and local stdlib trigger script**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-25T16:07:06Z
- **Completed:** 2026-03-25T16:09:07Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Prefect flow with git_pull, install_deps, restart_service, health_check tasks that runs on the VM
- Local trigger script using only Python stdlib (urllib) for zero-dependency remote deploys
- DEPLOY.md updated with Prefect deploy instructions, setup, and troubleshooting

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Prefect deploy flow for VM** - `4df4626` (feat)
2. **Task 2: Create local trigger script** - `ec20631` (feat)
3. **Task 3: Update DEPLOY.md with Prefect deploy instructions** - `08fa13f` (docs)

## Files Created/Modified
- `prefect/deploy_superbot_flow.py` - Prefect flow with deploy tasks, runs on VM via serve()
- `scripts/deploy_via_prefect.py` - Standalone trigger script using urllib, polls until completion
- `DEPLOY.md` - Added "Deploy via Prefect" section with prerequisites, setup, usage, troubleshooting

## Decisions Made
- Used stdlib urllib instead of httpx for the trigger script so it works without the project venv
- Used Prefect `flow.serve()` pattern (not work pool) for simpler single-flow deployment registration
- Added `--no-push` flag to trigger script (not in original plan) for parity with deploy.sh `--skip-push`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
One-time VM setup required: start the flow server on the VM via `python prefect/deploy_superbot_flow.py` (documented in DEPLOY.md).

## Next Phase Readiness
- Deploy pipeline ready for use once flow is started on VM
- No blockers

---
*Quick Task: 2*
*Completed: 2026-03-25*

## Self-Check: PASSED
