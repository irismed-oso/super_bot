---
status: complete
phase: 24-post-session-thread-scanning
source: 24-01-SUMMARY.md
started: 2026-03-25T20:20:00Z
updated: 2026-03-25T20:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Thread Scan Fires After Agent Session
expected: After an agent session completes, bot scans the thread via conversations_replies and calls Claude for extraction — visible in journald logs as "thread_scanner.complete" or "thread_scanner.nothing_extracted".
result: pass

### 2. Does Not Block Queue
expected: Thread scanning runs via asyncio.create_task (fire-and-forget). The next queued task can start immediately — scanning happens in the background.
result: pass

### 3. Only Human Messages Scanned
expected: Bot filters messages by bot_id and subtype — its own replies are excluded from extraction input. Only human messages are sent to Claude.
result: pass

### 4. Conservative Extraction Prompt
expected: Extraction prompt only accepts explicit directives ("always", "never", "the rule is") and stated facts. Questions, speculative statements, and current-task instructions are excluded.
result: pass

### 5. Task History Auto-Captured
expected: After every successful agent session, a one-line summary is stored with category="history" — queryable via "recall" or "list memories history".
result: pass

### 6. Deduplication on Insert
expected: If an extracted memory is a substring of an existing memory (or vice versa), it is not stored again — prevents duplicate accumulation.
result: pass

### 7. Graceful Degradation
expected: If anthropic package is not installed or API call fails, thread scanning logs a warning and returns — bot continues running, no crash.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
