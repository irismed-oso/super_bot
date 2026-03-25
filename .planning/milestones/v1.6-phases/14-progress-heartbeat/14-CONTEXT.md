# Phase 14: Progress Heartbeat - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

During long agent sessions (up to 30 min), the bot edits a single progress message every 5 minutes showing last activity, turn count, and elapsed time. Users never wonder if the bot is stuck. Fast-path commands are excluded — heartbeat is for full agent sessions only.

</domain>

<decisions>
## Implementation Decisions

### Message format
- Single-line format: `:hourglass: Still working... [Last Activity] | Turn X/25 | Ym Zs`
- Prefix with `:hourglass:` emoji for visual anchor in thread
- Same message as existing progress milestones — heartbeat edits the same `progress_msg` that milestone detection already uses
- No separate heartbeat message — one message does both jobs

### Timing behavior
- First heartbeat fires after 1 minute (quick first signal)
- Subsequent heartbeats every 3 minutes (1m, 4m, 7m, 10m, 13m, 16m, 19m, 22m, 25m, 28m)
- Agent sessions only — fast-path commands respond too quickly to need heartbeat
- On task completion: edit message one final time to show "Completed in Xm Ys" then post result as separate message
- On timeout/cancel: heartbeat stops cleanly, no ghost edits after final result posted

### Activity tracking
- Reuse existing milestone detection from `progress.py` (Reading files, Making changes, Running tests, Committing changes, Creating PR)
- Default activity before any milestone fires: "Starting up..."
- Turn counter updates in real-time via on_message callback (each AssistantMessage increments count)
- Heartbeat reads latest turn count and last milestone when it fires

### Milestone + heartbeat interaction
- When a milestone fires (tool use detected), update the message immediately with new activity label
- Heartbeat timer continues independently — next tick updates elapsed time and turn count even if activity label hasn't changed

### Claude's Discretion
- asyncio timer implementation details (Task, Event, etc.)
- How to share mutable state between on_message callback and heartbeat timer
- Whether to log heartbeat ticks to structlog

</decisions>

<specifics>
## Specific Ideas

- The heartbeat should feel like a "still alive" signal, not a detailed status report
- Keep it compact — Nicole glances at the thread and sees the bot is still going
- The existing `progress_msg` dict (with `ts` and `channel`) is the natural hook point

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-progress-heartbeat*
*Context gathered: 2026-03-24*
