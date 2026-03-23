---
phase: 05-vm-validation-and-mcp-wiring
plan: 01
subsystem: infra
tags: [mcp, feature-flag, deployment, gcloud, systemd]

requires:
  - phase: 03-agent-sdk-integration
    provides: "Claude Agent SDK wrapper with MCP server wiring in bot/agent.py"
provides:
  - "MIC_TRANSFORMER_MCP_DISABLED feature flag for troubleshooting"
  - "Phase 5 VM deployment script covering all setup steps"
affects: [05-02, phase-7]

tech-stack:
  added: [mcp-cli-1.26]
  patterns: [env-var-feature-flag, gcloud-ssh-deploy-script]

key-files:
  created: [scripts/deploy_v1.2_phase5.sh]
  modified: [config.py, bot/agent.py]

key-decisions:
  - "Feature flag defaults to False (MCP enabled by default when path exists)"
  - "Flag checked before path detection to short-circuit cleanly"
  - "No env field on mic-transformer server config (subprocess inherits parent env)"

patterns-established:
  - "Feature flag pattern: env var -> config.py bool -> checked at wiring point"
  - "Deploy script pattern: 8-step sequence with gcloud compute ssh"

requirements-completed: [MCPW-01, MCPW-02]

duration: 2min
completed: 2026-03-23
---

# Phase 5 Plan 01: Feature Flag and Deploy Script Summary

**MIC_TRANSFORMER_MCP_DISABLED env var feature flag with 8-step VM deployment script for Phase 5 rollout**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-23T19:48:35Z
- **Completed:** 2026-03-23T19:50:13Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added MIC_TRANSFORMER_MCP_DISABLED boolean flag to config.py (defaults to False)
- Updated _build_mcp_servers() to check flag before path detection, with structured logging
- Created deploy_v1.2_phase5.sh covering all 8 VM setup steps

## Task Commits

Each task was committed atomically:

1. **Task 1: Add feature flag and update MCP wiring** - `f6e1288` (feat)
2. **Task 2: Create Phase 5 deploy script** - `c95191a` (feat)

## Files Created/Modified
- `config.py` - Added MIC_TRANSFORMER_MCP_DISABLED boolean flag
- `bot/agent.py` - Feature flag check before path detection in _build_mcp_servers()
- `scripts/deploy_v1.2_phase5.sh` - 8-step VM deployment script

## Decisions Made
- Feature flag defaults to False so MCP is enabled by default when path exists on disk
- Flag is checked before path detection to short-circuit cleanly with structured log message
- No env field added to mic-transformer server config (subprocess inherits parent env, credentials come from config/*.yml)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Feature flag and deploy script ready for VM validation in plan 05-02
- Deploy script must be run on actual VM to complete Phase 5 validation
- Config files (config/*.yml) must be SCP'd to VM before mic-transformer MCP can function

---
*Phase: 05-vm-validation-and-mcp-wiring*
*Completed: 2026-03-23*
