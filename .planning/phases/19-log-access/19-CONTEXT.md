# Phase 19: Log Access - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Read journald service logs and Prefect flow run logs from Slack, with output parsed and truncated to fit Slack messages. Supports filtering by keyword and time range. Covers superbot and mic_transformer services.

</domain>

<decisions>
## Implementation Decisions

### Output formatting
- Log format: Claude's discretion (parsed summary vs raw, whichever is most readable in Slack)
- Default line count: Claude's discretion
- Output truncation mandatory — must fit Slack message limits

### Filter syntax
- Natural language: "logs superbot errors last hour", "logs mic 50 lines"
- Supports filtering by service name using same aliases as deploy (superbot, mic, etc.)

### Pipeline routing
- Log commands go through the **agent pipeline** (not fast-path)
- Applies to both journald and Prefect logs

### Prefect logs
- Accept flow run ID/name directly: "prefect logs turquoise-fox"
- Also accept contextual lookups: "show logs for last DME crawl"
- Through agent pipeline

### Secret scrubbing
- Claude's discretion on scrubbing approach and aggressiveness

### Claude's Discretion
- Log output format (parsed vs raw)
- Default line count
- Secret scrubbing patterns and aggressiveness
- How to handle very large log output (truncate vs file upload)

</decisions>

<specifics>
## Specific Ideas

- Since logs go through agent pipeline, the agent can use its judgment to parse natural language filters, look up Prefect run IDs by context, and format output appropriately
- Same repo aliases as deploy/rollback should work for service names

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 19-log-access*
*Context gathered: 2026-03-25*
