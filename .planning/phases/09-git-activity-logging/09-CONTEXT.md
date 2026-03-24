# Phase 9: Git Activity Logging - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Bot captures every commit, PR, and file change it produces during sessions into a persistent activity log. The digest display of this data is Phase 10 — this phase only handles capture and storage.

</domain>

<decisions>
## Implementation Decisions

### Log trigger mechanism
- Real-time capture via on_message callback (already detects tool use blocks for commits/PRs)
- Post-session lightweight verification pass to confirm captured entries are valid (commits still exist)
- Both mechanisms work together: real-time is primary, post-session is sanity check

### Multi-repo scope
- Track all repos the bot touches, not just mic_transformer
- Repo identification via working directory path (not git remote parsing)

### Data granularity
- Commits: hash, message (first line), repo name, branch name, list of changed file paths
- PRs: URL, title, repo name
- File changes: file names only, no diff stats or line counts

### Claude's Discretion
- Whether to parse tool output from SDK stream vs run git commands after detecting commits
- Whether to write log entries continuously during session or batch at end
- Whether to extend existing activity_log.py entries or create separate git activity files
- Whether to store full commit message or just subject line (leaning subject for digest readability)

</decisions>

<specifics>
## Specific Ideas

- The bot already has on_message callback infrastructure in progress.py that inspects ToolUseBlock objects and detects git commits/pushes/PR creation
- The existing activity_log.py uses date-stamped JSONL files at /home/bot/activity_logs/
- PR URL regex already exists in progress.py (PR_URL_RE) for GitHub and GitLab URLs
- The result dict from run_agent_with_timeout() contains the full session output text

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 09-git-activity-logging*
*Context gathered: 2026-03-24*
