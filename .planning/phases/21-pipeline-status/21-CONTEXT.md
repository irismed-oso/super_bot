# Phase 21: Pipeline Status - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Fast-path-style "pipeline status" command showing Prefect flow runs grouped by status (completed/failed/running), with flow names, timestamps, and run IDs. Emphasizes failures. Supports natural language time windows.

</domain>

<decisions>
## Implementation Decisions

### Grouping & layout
- Group by status: Failed first (emphasized), then Running, then Completed
- Each run shows flow name, timestamp, and run ID/name
- Through the **agent pipeline** (not fast-path) — agent handles natural language time windows

### What to highlight
- Failed runs emphasized: at the top with error details
- Completed runs as a summary (count + list)
- Show run IDs/names for all runs so Nicole can follow up with "prefect logs [id]"

### Time window
- Natural language: "pipeline status today", "pipeline status this week", "pipeline status 03.25"
- Default: last 24 hours when no time specified
- Agent interprets the time window from natural language

### Claude's Discretion
- Exact formatting and emoji choices
- How many completed runs to list before summarizing
- Whether to include run durations
- How to handle large numbers of runs (pagination/truncation)

</decisions>

<specifics>
## Specific Ideas

- Existing `bot/prefect_api.py` already has the Prefect API client and auth pattern
- The agent already has bash access and can use the log_tools CLI for follow-up
- Since this goes through the agent, the agent can combine pipeline status with follow-up actions ("pipeline status — and show me the logs for any failures")

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-pipeline-status*
*Context gathered: 2026-03-26*
