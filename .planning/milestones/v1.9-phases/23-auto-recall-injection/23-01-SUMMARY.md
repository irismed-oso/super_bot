---
phase: 23-auto-recall-injection
plan: 01
subsystem: memory
tags: [sqlite, fts5, recall, prompt-injection, structlog]

requires:
  - phase: 22-sqlite-foundation-and-memory-commands
    provides: "memory_store module with list_all(), search(), FTS5 backend"
provides:
  - "build_recall_block() function for auto-injecting memories into agent prompts"
  - "Recall wiring in handlers.py _build_prompt for agent sessions only"
affects: [24-thread-scanning, agent-prompt-quality]

tech-stack:
  added: []
  patterns: ["recall block injection between user text and agent rules in prompt"]

key-files:
  created: [bot/memory_recall.py]
  modified: [bot/handlers.py]

key-decisions:
  - "Rules always included regardless of token budget; extras truncated first"
  - "Recall block positioned between user text and AGENT_RULES for prompt hierarchy"
  - "Memory count extracted from block content via line counting (no tuple return)"

patterns-established:
  - "Prompt injection pattern: recall block inserted between user text and hard rules"
  - "Token budget guard with category-aware truncation (rules exempt)"

requirements-completed: [RECALL-01, RECALL-02, RECALL-03, RECALL-04]

duration: 4min
completed: 2026-03-25
---

# Phase 23 Plan 01: Auto-Recall Injection Summary

**Auto-recall system that fetches rules + FTS5-ranked memories and injects them as a formatted prompt block into every agent session**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-25T19:05:46Z
- **Completed:** 2026-03-25T19:10:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created bot/memory_recall.py with build_recall_block() that always fetches rules, fills remaining slots via FTS5 search, caps at 8 memories with 500-token budget, and formats with category brackets and citation footer
- Wired recall into handlers.py so agent sessions get recalled memories injected between user text and agent rules, while fast-path commands remain unaffected
- Graceful degradation: recall failures never crash the agent pipeline

## Task Commits

Each task was committed atomically:

1. **Task 1: Create bot/memory_recall.py with recall block builder** - `ffa610a` (feat)
2. **Task 2: Wire auto-recall into handlers.py agent prompt flow** - `7a143c1` (feat)

## Files Created/Modified
- `bot/memory_recall.py` - Recall block builder: fetches rules + FTS5 search, formats as prompt block with token budget
- `bot/handlers.py` - Added memory_recall import, recall call before prompt build, recall_block parameter in _build_prompt

## Decisions Made
- Rules always included regardless of token budget; extras truncated first from the bottom
- Recall block positioned between user text and AGENT_RULES in prompt hierarchy
- Memory count extracted from block content via line counting rather than returning a tuple

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Auto-recall complete, memories stored via Phase 22 commands now automatically influence agent behavior
- Ready for Phase 24 (Thread Scanning) to auto-capture memories from conversations

---
*Phase: 23-auto-recall-injection*
*Completed: 2026-03-25*
