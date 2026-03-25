---
phase: 19-log-access
plan: 01
subsystem: infra
tags: [journald, prefect, structlog, log-parsing, secret-scrubbing]

# Dependency graph
requires:
  - phase: 04-agent-pipeline
    provides: "Agent pipeline with _AGENT_RULES prompt injection"
  - phase: 16-deploy
    provides: "deploy_state.REPO_CONFIG with service aliases"
  - phase: 17-prefect-deploy
    provides: "prefect_api module with API constants"
provides:
  - "Log retrieval CLI for journald and Prefect flow runs"
  - "Structlog JSON parsing to readable format"
  - "Secret scrubbing for Slack-safe output"
  - "Slack message truncation with line count indicator"
affects: [agent-pipeline, deploy, monitoring]

# Tech tracking
tech-stack:
  added: [argparse-cli]
  patterns: [cli-tool-for-agent, format-then-scrub-then-truncate]

key-files:
  created:
    - bot/log_tools.py
    - tests/test_log_tools.py
    - tests/__init__.py
  modified:
    - bot/handlers.py

key-decisions:
  - "CLI entry point over MCP tool -- agent already has bash, simpler wiring"
  - "Truncation from beginning (keep most recent) with 2800 char limit for Slack"
  - "Conservative secret scrubbing -- better to miss a secret than mangle data"
  - "Default 50 lines when user doesn't specify count"

patterns-established:
  - "CLI tools for agent: python -m bot.<tool> with argparse subcommands"
  - "Log pipeline: parse structlog -> scrub secrets -> truncate for Slack"

requirements-completed: [LOGS-01, LOGS-02, LOGS-03, LOGS-04]

# Metrics
duration: 4min
completed: 2026-03-25
---

# Phase 19 Plan 01: Log Access Summary

**Journald and Prefect log retrieval via CLI with structlog parsing, secret scrubbing, and Slack-safe truncation**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-25T21:05:43Z
- **Completed:** 2026-03-25T21:09:43Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Journald log retrieval with service alias resolution, grep filtering, and time range support
- Prefect flow run log retrieval by UUID or name with level mapping
- Structlog JSON parsed to "timestamp LEVEL event key=value" readable format
- Secret scrubbing for Slack tokens, API keys, AWS keys, bearer tokens, URL passwords
- Output truncated to 2800 chars with "showing last N of M lines" indicator
- 26 unit tests covering all parsing, scrubbing, truncation, and resolution logic

## Task Commits

Each task was committed atomically:

1. **Task 1: Create log_tools module with journald and Prefect log retrieval** - `e605145` (feat)
2. **Task 2: Wire log tools into agent pipeline with usage instructions** - `2ae0cbe` (feat)

## Files Created/Modified
- `bot/log_tools.py` - Log retrieval, structlog parsing, secret scrubbing, truncation, CLI entry point
- `tests/test_log_tools.py` - 26 unit tests for all log_tools functions
- `tests/__init__.py` - Test package init
- `bot/handlers.py` - Added log tool instructions to _AGENT_RULES

## Decisions Made
- CLI entry point over MCP tool: agent already has bash access, CLI is simpler wiring than registering MCP tools
- Truncation from beginning: keeps most recent lines which are most useful for debugging
- 2800 char limit: leaves headroom under Slack's 3000 char message limit
- Conservative secret scrubbing: patterns match known formats (xox*, sk-*, AKIA*, Bearer) rather than aggressive heuristics

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed pytest for test execution**
- **Found during:** Task 1
- **Issue:** pytest not installed in venv
- **Fix:** pip install pytest
- **Verification:** All 26 tests pass

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal -- test dependency installation only.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Log tools ready for agent use via CLI
- Agent rules updated with usage instructions
- Service alias resolution reuses existing REPO_CONFIG

---
*Phase: 19-log-access*
*Completed: 2026-03-25*
