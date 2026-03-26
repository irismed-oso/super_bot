---
status: complete
phase: 23-auto-recall-injection
source: 23-01-SUMMARY.md
started: 2026-03-25T20:10:00Z
updated: 2026-03-25T20:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Auto-Recall Applies Stored Rule
expected: Store a rule about autopost dry_run, then ask bot to run autopost. Bot follows the rule without being told and shows a citation.
result: pass

### 2. Rules Always Included
expected: Store 2+ rules. Ask the bot any task. All rules should appear in the recall block regardless of relevance to the task.
result: pass

### 3. FTS5 Relevance Matching
expected: Store several memories across categories. Ask a task related to one specific topic. Bot should recall the relevant memory based on keyword match.
result: pass

### 4. Fast-Path No Recall
expected: Type "crawl eyemed DME 03.20" or "status on DME" or "list memories". These fast-path commands should respond instantly with no recall overhead.
result: pass

### 5. Graceful When No Memories
expected: If the memory store is empty, agent sessions should work normally -- no errors, no empty recall block shown.
result: pass

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
