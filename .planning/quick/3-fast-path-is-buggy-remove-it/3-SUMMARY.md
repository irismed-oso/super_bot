---
phase: quick
plan: 3
subsystem: bot-handlers
tags: [cleanup, bug-fix, fast-path-removal]
dependency_graph:
  requires: []
  provides:
    - "All messages flow through agent pipeline"
  affects:
    - bot/handlers.py
    - bot/progress.py
tech_stack:
  added: []
  patterns:
    - "Single message pipeline (no fast-path bypass)"
key_files:
  created: []
  modified:
    - bot/handlers.py
    - bot/progress.py
  deleted:
    - bot/fast_commands.py
decisions:
  - "Removed fast-path system entirely rather than fixing individual bugs"
  - "Simplified _timeout_suggestion to static fallback (location-aware hints removed with fast_commands)"
metrics:
  duration: 75s
  completed: 2026-03-25
---

# Quick Task 3: Remove Buggy Fast-Path Command System

Deleted the fast-path command bypass that intercepted certain messages (eyemed crawl, eyemed status, bot status, batch crawl) before they reached the agent pipeline. All messages now flow through the full agent pipeline.

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove fast-path bypass from handlers and delete fast_commands module | 6b2c408 | bot/handlers.py, bot/progress.py, bot/fast_commands.py (deleted) |

## Changes Made

### bot/handlers.py
- Removed `from bot.fast_commands import try_fast_command` import
- Removed the entire fast-path block in `_run_agent_real` (~33 lines): the call to `try_fast_command()`, the `if fast_result is not None:` branch, and all Slack message posting logic inside it
- Message flow now goes directly from DB logging to session lookup

### bot/fast_commands.py
- Deleted entirely (441 lines). Contained: action-request detection, location aliases, eyemed crawl/status handlers, bot status handler, batch crawl handler, and the `try_fast_command` dispatcher.

### bot/progress.py
- Simplified `_timeout_suggestion()`: removed `from bot.fast_commands import LOCATION_ALIASES` import and the location alias lookup loop
- Function now returns the static fallback: "Check `/sb-status` for current state."

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- `python -m py_compile bot/handlers.py` -- passes (no syntax errors)
- `python -m py_compile bot/progress.py` -- passes (no syntax errors)
- `grep -r "fast_command" bot/` -- zero matches
- `grep -r "fast_path" bot/` -- zero matches
- `bot/fast_commands.py` -- confirmed deleted

## Self-Check: PASSED
