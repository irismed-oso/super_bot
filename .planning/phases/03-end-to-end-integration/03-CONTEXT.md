# Phase 3: End-to-End Integration - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire Phase 1 (Slack bot) to Phase 2 (Agent SDK) for the full @mention → Claude Code → Slack reply loop. Add progress updates in threads, git operations with MR creation, auto-testing, and worktree isolation for concurrent tasks. No new operational capabilities (Prefect, deploy, etc.) — those are Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Progress Updates
- Key milestones only — started, reading files, making changes, running tests, done (4-6 updates max per task)
- Brief with context — "Reading bot/agent.py to understand the timeout logic" (explains why, not just what)
- All updates stay in the thread — channel stays clean
- Completion message includes diff summary only when code was changed; Q&A tasks just get the answer

### MR Creation Flow
- Branch naming: `superbot/task-description` — clearly bot-authored
- Target branch: `develop`
- MR description includes: what was changed, link to triggering Slack thread, test results (if run), files changed
- Let Claude Code handle MR creation using whatever git/API approach it prefers — no prescriptive tool choice
- Claude already has GitLab PAT from Phase 1 .env

### Auto-Test Behavior
- Claude decides when to run pytest — judges whether tests are relevant to what changed
- On test failure: Claude decides whether to post failure + stop, or attempt a fix
- Test results in Slack: one-line pass/fail summary ("Tests: 42 passed, 0 failed")

### Worktree Isolation
- Code-change tasks get isolated worktrees; Q&A/read-only tasks run in the main repo
- Worktree naming: `worktree-{thread_ts}` — maps back to the Slack thread
- Cleanup: keep worktree until MR is merged (enables follow-up replies in thread)
- On task failure with uncommitted changes: git stash + report to Slack. Worktree stays for recovery.

### Claude's Discretion
- How to detect whether a task is "code change" vs "Q&A" for worktree decision
- Which agent SDK streaming events to use for progress updates
- How to construct Slack thread permalink for MR descriptions
- Exact pytest invocation command and output parsing
- Whether to attempt fixing failing tests or report and stop

</decisions>

<specifics>
## Specific Ideas

- The integration should feel seamless — Nicole shouldn't notice the switch from Phase 1 stub to real Claude
- Progress updates should make long tasks feel responsive, not chatty
- MR descriptions should have enough context that a reviewer understands what was done and why without opening Slack

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-end-to-end-integration*
*Context gathered: 2026-03-20*
