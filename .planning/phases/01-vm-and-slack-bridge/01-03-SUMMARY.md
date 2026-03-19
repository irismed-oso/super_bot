---
phase: 01-vm-and-slack-bridge
plan: 03
subsystem: infra
tags: [slack-bolt, socket-mode, systemd, asyncio, lazy-listener]

requires:
  - phase: 01-vm-and-slack-bridge/01-02
    provides: "bot package with access_control, deduplication, task_state, formatter modules"
provides:
  - "Runnable Slack bot entry point (bot/app.py) with Socket Mode"
  - "Lazy listener handler chain with 4 guards (bot filter, dedup, access control, channel filter)"
  - "Slash commands: /status, /cancel, /help"
  - "systemd service unit ready for deployment"
  - "Slack app manifest for api.slack.com configuration"
  - "Pinned requirements.txt"
affects: [01-04, 02-agent-sdk]

tech-stack:
  added: [slack-bolt 1.27.0, aiohttp, structlog, python-dotenv]
  patterns: [lazy-listener-pattern, register-function-for-handlers, guard-chain]

key-files:
  created: [bot/app.py, bot/handlers.py, requirements.txt, systemd/superbot.service, slack_manifest.yaml]
  modified: []

key-decisions:
  - "Lazy listener pattern: ack handler runs inline (fast), agent stub runs as lazy function (async)"
  - "register(app) pattern avoids circular imports between app.py and handlers.py"
  - "Guard ordering: bot filter -> dedup -> access control -> channel filter (cheapest first)"

patterns-established:
  - "Lazy listener: @app.event('app_mention', lazy=[fn]) for immediate ack + async processing"
  - "Guard chain: all guards call ack() and return early, keeping Slack happy"
  - "register(app) handler registration: handlers never import app module directly"

requirements-completed: [SLCK-01, SLCK-02, SLCK-05, SLCK-07, SLCK-08, INFRA-04]

duration: 2min
completed: 2026-03-19
---

# Phase 01 Plan 03: Slack Bot App + Handlers Summary

**Slack bot with lazy listener guard chain, Socket Mode entry point, 3 slash commands, systemd service, and app manifest**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-19T15:18:18Z
- **Completed:** 2026-03-19T15:20:18Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Lazy listener pattern with 4-guard chain (bot filter, deduplication, access control, channel filter) ensuring correct ack timing
- Slash commands /status, /cancel, /help wired to task_state and formatter modules from 01-02
- systemd service unit with security hardening (NoNewPrivileges, PrivateTmp) and journald logging
- Slack app manifest ready to paste into api.slack.com with Socket Mode, app_mention subscription, and required OAuth scopes

## Task Commits

Each task was committed atomically:

1. **Task 1: App entry point, handlers, and requirements** - `194ffdf` (feat)
2. **Task 2: systemd service unit and Slack app manifest** - `96f2da9` (feat)

## Files Created/Modified
- `bot/app.py` - AsyncApp entry point with load_dotenv before config import, Socket Mode handler
- `bot/handlers.py` - register(app) with lazy listener, 4 guards, emoji ack, agent stub, 3 slash commands
- `requirements.txt` - Pinned slack-bolt==1.27.0, aiohttp, cachetools, python-dotenv, structlog
- `systemd/superbot.service` - User=bot, EnvironmentFile, Restart=always, security hardening
- `slack_manifest.yaml` - Socket Mode, app_mention, /status /cancel /help, OAuth scopes

## Decisions Made
None - followed plan as specified.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Bot application is structurally complete and ready for deployment
- Phase 2 replaces the agent stub in _run_agent_stub with real Claude Agent SDK invocation
- systemd service file needs to be copied to /etc/systemd/system/ during VM provisioning (handled by startup.sh from 01-01)

## Self-Check: PASSED

All 6 files verified present. Both task commits (194ffdf, 96f2da9) confirmed in git log.

---
*Phase: 01-vm-and-slack-bridge*
*Completed: 2026-03-19*
