# Phase 18: Rollback - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Git-based rollback to a previous commit + redeploy, with automatic roll-forward if the rollback fails health checks. Covers both super_bot (self-restart) and mic_transformer. Uses the deploy infrastructure from Phase 17.

</domain>

<decisions>
## Implementation Decisions

### Rollback target
- User can specify a target SHA: "rollback super_bot abc1234"
- If no SHA specified, default to the pre-deploy SHA from deploy history (the last recorded deploy's previous state)
- If no deploy history exists, show error with suggestion to specify a SHA

### Auto-roll-forward
- If rollback fails the post-deploy health check, automatically revert to the pre-rollback SHA
- If auto-roll-forward ALSO fails: stop and report to Slack, manual SSH intervention needed (no infinite retry)
- Health check approach: Claude's discretion on what constitutes "healthy"

### Command UX
- Show what it's about to rollback to (target SHA + what changes) before proceeding automatically -- no confirmation gate, just informational
- Edit-in-place progress (same pattern as deploy)
- Pipeline routing: Claude's discretion (follow whatever pattern makes sense given deploy's routing)

### Self-rollback (super_bot)
- Mechanism: Claude's discretion -- reuse Prefect + deploy-state pattern from Phase 17 if it fits, or adapt as needed

### Claude's Discretion
- Whether rollback goes through agent pipeline or fast-path (follow deploy pattern)
- Health check specifics (systemctl check, journal error scan, etc.)
- Self-rollback mechanism (Prefect reuse vs alternative)
- How to handle rollback when pip deps change between versions

</decisions>

<specifics>
## Specific Ideas

- Deploy history from Phase 17 (`record_deploy` / `get_last_deploy`) already tracks the SHA -- rollback should use this to find the "previous" version
- The self-deploy Prefect pipeline already handles git checkout + restart -- rollback for super_bot is essentially "deploy to a specific SHA instead of origin/main"

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 18-rollback*
*Context gathered: 2026-03-25*
