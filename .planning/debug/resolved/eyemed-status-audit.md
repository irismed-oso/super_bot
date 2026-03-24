---
status: resolved
trigger: "EyeMed status command slow (4+ min), missing scanned dates, no date range support"
created: 2026-03-23T00:00:00Z
updated: 2026-03-23T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - Root cause is twofold: (1) eyemed status goes through Claude Code agent + MCP tool chain adding minutes of LLM overhead, (2) eyemed_status MCP tool only takes a single date, missing the crawler's 10-day lookback window
test: Traced full execution path from Slack message to MCP tool
expecting: N/A - root cause confirmed
next_action: Build a fast standalone script that queries eyemed_scan_results DB table directly with date range support

## Symptoms

expected:
1. EyeMed status should report scanned dates from the default lookback window (not just today)
2. Response should be fast (seconds, not minutes)
3. Should support date ranges as arguments

actual:
1. Only reported today's date with all zeros - missed the lookback dates the scanner checks
2. First response took 4 minutes (10:15 to 10:19)
3. Follow-up question timed out after 10 minutes with "(nothing)" output
4. No date range support

errors: "Task timed out. Here's what was completed: (nothing)" on follow-up question

reproduction: Ask Super Bot in Slack "what's the eyemed status for today"

started: Observed 2026-03-24

## Eliminated

## Evidence

- timestamp: 2026-03-23T00:10:00Z
  checked: bot/handlers.py + bot/agent.py execution path
  found: Every Slack message goes through Claude Code agent (run_agent_with_timeout) which spawns a full Claude Code process with MCP servers. The agent must boot, read CLAUDE.md, understand the request, pick the right MCP tool, call it, interpret results, and format response. This explains 4+ min latency.
  implication: The LLM overhead is the primary performance bottleneck

- timestamp: 2026-03-23T00:15:00Z
  checked: MCP tools/status.py eyemed_status tool (line 703)
  found: eyemed_status takes a single date parameter. It queries GCS blobs, Google Drive folders, checks AIOUT files for that one date. When user asks "status for today" the agent passes today's date only.
  implication: Misses the crawler's 10-day lookback window entirely

- timestamp: 2026-03-23T00:17:00Z
  checked: prefect/eyemed_crawler_deployments.py
  found: Crawler runs with days_back=10. It scans 10 days of disbursements per location. The status tool only checks 1 day.
  implication: Status should cover the same date range the crawler covers

- timestamp: 2026-03-23T00:20:00Z
  checked: MCP tools/status.py eyemed_scan_results tool (line 1758)
  found: There IS an eyemed_scan_results tool that queries the eyemed_crawler_scan_results DB table with date range support. This table has per-location, per-remit-date results showing files_count, amount_total, status. This is the fast data source.
  implication: A standalone script can query this DB table directly for instant results

- timestamp: 2026-03-23T00:22:00Z
  checked: MCP tools/status.py eyemed_status_range tool (line 1511)
  found: There is also an eyemed_status_range tool that checks GCS+GDrive across a date range. This is comprehensive but slow (GCS+GDrive API calls).
  implication: For a fast script, use the DB table (eyemed_crawler_scan_results) not GCS/GDrive APIs

## Resolution

root_cause: Two issues: (1) EyeMed status requests go through full Claude Code agent + MCP tool chain, adding 4+ min of LLM overhead for what should be a DB query. (2) The eyemed_status MCP tool only takes a single date, missing the crawler's 10-day lookback window. The combination means slow + incomplete results.
fix: Create a standalone Python script (scripts/eyemed_status.py) that queries the eyemed_crawler_scan_results DB table directly with date range support (default: last 10 days to match crawler lookback). Callable from CLI for instant results.
verification: Tested 3 modes locally against live DB - all return correct results in <2 seconds: (1) default 10-day lookback shows 142 entries across dates, (2) location filter (ecec) returns 11 entries, (3) date range with --json returns structured output. Per-date deduped count bug also fixed.
files_changed:
- mic_transformer/scripts/eyemed_scan_status.py (NEW)
