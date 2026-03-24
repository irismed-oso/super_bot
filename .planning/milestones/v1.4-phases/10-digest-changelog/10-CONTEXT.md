# Phase 10: Digest Changelog - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a changelog section to the existing daily Slack digest that shows commits and PRs the bot created yesterday, grouped by repository, with a git log scan at build time to catch anything missed by session logging. Phase 9 (Git Activity Logging) provides the structured data.

</domain>

<decisions>
## Implementation Decisions

### Changelog format
- Commits display as short hash + subject: `808fb31` fix timeout bug
- PRs display as title with clickable Slack link: `<url|Fix timeout bug>`
- Cap at 15 commits per digest; show "...and N more" if exceeded
- PRs are not capped (unlikely to exceed a handful per day)

### Repo grouping
- Bold repo name as header, entries indented below
- Skip the repo header if all activity is in a single repo (less noise)
- Repos ordered alphabetically or by commit count -- Claude's discretion

### Empty/edge states
- When there's no git activity: Claude decides whether to omit the section or show a brief message

### Git scan fallback
- Scan all cloned repos on the VM at digest build time (not just repos in activity log)
- Filter commits by git author name/email matching the bot's identity
- Commits found by scan but missing from the activity log should be subtly marked as "recovered"
- Scan covers yesterday's date range (matching the digest's reporting period)

### Claude's Discretion
- Changelog placement relative to existing task summary (before or after)
- Whether commits and PRs are separate sub-sections or mixed chronologically
- Exact empty-state behavior (omit section vs show "No changes")
- Repo ordering within the changelog

</decisions>

<specifics>
## Specific Ideas

- The existing digest already uses Slack mrkdwn formatting (bold, bullets, etc.)
- Phase 9 created `read_day_by_type` in activity_log.py for querying commits and PRs by type
- The existing digest format is in bot/daily_digest.py with stats, per-user breakdown, and task list
- PR_URL_RE already exists in bot/progress.py for URL matching

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 10-digest-changelog*
*Context gathered: 2026-03-24*
