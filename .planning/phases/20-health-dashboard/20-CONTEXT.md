# Phase 20: Health Dashboard - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Fast-path "bot health" command showing a comprehensive health snapshot: uptime, status, queue, version, memory, disk, task success/fail, active monitors, and last deploy info. Replaces the existing simple bot status handler.

</domain>

<decisions>
## Implementation Decisions

### Info displayed
- Everything: uptime, current status, queue depth, version (git SHA), last restart, memory, disk, CPU, recent task success/fail count, active background monitors, last deploy info
- Deploy info inclusion: Claude's discretion

### Output layout
- Compact list format, one line per metric, emoji prefixed
- Replaces the existing `_handle_bot_status` handler entirely (not a separate command)
- Same trigger patterns ("are you broken?", "bot status", "bot health", etc.)

### Error counting
- Source: Claude's discretion (journald errors, task failures, or both)

### Claude's Discretion
- Whether to include deploy info or leave that to `deploy status`
- Error counting source and time window
- Exact emoji choices and line ordering
- CPU metric approach (if feasible without psutil)

</decisions>

<specifics>
## Specific Ideas

- Existing `_handle_bot_status` in fast_commands.py already handles "are you broken?" etc. — this phase upgrades it in-place
- task_state module already tracks uptime and recent tasks
- queue_manager already exposes current task and queue depth
- background_monitor already exposes active monitors

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 20-health-dashboard*
*Context gathered: 2026-03-25*
