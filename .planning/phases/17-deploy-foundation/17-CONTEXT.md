# Phase 17: Deploy Foundation - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deploy super_bot and mic_transformer from Slack with a single command. Includes deploy status, deploy preview, active-task guard, and self-restart handling for super_bot. Also verifies v1.4-v1.6 features on the production VM as part of the deploy workflow.

</domain>

<decisions>
## Implementation Decisions

### Self-deploy UX
- Bot triggers deploy via the **Prefect deploy pipeline** (quick task 2), NOT direct git pull/systemctl
- Pre-restart message is detailed: shows current SHA -> target SHA, warns about restart, gives timeout guidance ("If I don't reply in 30s, check logs")
- Post-restart: bot checks for pending deploy-state file on startup, immediately posts "I'm back, running commit xyz" to the original thread
- Post-restart confirmation fires as soon as Slack connection is re-established (no delay for health check)
- Recovery on failure is manual SSH — no auto-rollback mechanism for self-deploy
- For mic_transformer: poll Prefect API for completion (like batch crawl monitoring); for super_bot: deploy-state file checked on startup

### mic_transformer service
- mic_transformer runs as a systemd service on the VM (service name TBD — needs verification on VM)
- Health check approach TBD — need to verify if HTTP endpoint or systemctl-only
- Deploy always pulls from main branch (no branch targeting)

### Command syntax
- Accept both short aliases ("superbot", "mic") and full names ("super_bot", "mic_transformer")
- Command pattern: Claude's discretion on exact syntax
- Deploy commands go through the **agent pipeline** (not fast-path) — gives flexibility for complex requests like "deploy and run tests first"

### Output formatting
- Deploy progress: single message **edited in place** as each step completes (like heartbeat updates)
- Deploy status: minimal — commit hash + branch + "X commits behind"

### Safety behavior
- Active agent task blocks deploy with a warning; "deploy force [repo]" overrides
- If nothing to deploy (already on latest): abort with "Already on latest (abc1234). Nothing to deploy."
- Dirty state on VM: warn about uncommitted changes but proceed anyway

### Claude's Discretion
- Exact command regex patterns and aliases
- Deploy-state file format and location
- How to stash/handle dirty state during deploy
- mic_transformer health check implementation (once service name is known)

</decisions>

<specifics>
## Specific Ideas

- Prefect deploy pipeline was just created as quick task 2 (commit 08fa13f) — deploy command should trigger this, not replicate the logic
- Edit-in-place pattern already proven with heartbeat and fast-path commands — deploy output should feel the same
- Deploy is an agent task, not fast-path — this means it goes through the queue and respects the active-task guard naturally

</specifics>

<deferred>
## Deferred Ideas

- Auto-rollback on failed self-deploy — keeping manual for now, may add in Phase 18 (Rollback)
- Branch targeting ("deploy superbot branch feature-x") — always main for now
- Deploy irismed-service and oso-fe-gsnap — different infrastructure, paths undefined

</deferred>

---

*Phase: 17-deploy-foundation*
*Context gathered: 2026-03-25*
