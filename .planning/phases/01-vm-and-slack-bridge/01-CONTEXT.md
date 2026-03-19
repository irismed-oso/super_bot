# Phase 1: VM and Slack Bridge - Context

**Gathered:** 2026-03-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Provision a GCP VM and deploy a Slack bot bridge with correct security, access control, and event handling patterns. The bot connects via Socket Mode, responds to @mentions from authorized users, handles event deduplication, and provides /status, /cancel, and /help slash commands. No Claude Code integration yet — that's Phase 2.

</domain>

<decisions>
## Implementation Decisions

### VM Provisioning
- Terraform for infrastructure-as-code in the existing IrisMed GCP project
- Ubuntu 24.04 LTS in us-west1 region
- Start with e2-small or e2-medium, resize as needed
- Startup script for auto-configuration (Python, git, clone repo, install deps)
- Dedicated low-privilege `bot` Linux user owns the repo clone and all bot files

### Credential Strategy
- Two separate .env files:
  - Bot .env in bot home directory: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, GITLAB_TOKEN, ALLOWED_USERS
  - mic_transformer .env in repo clone directory: existing DB URLs, Prefect keys, service credentials
- No GCP Secret Manager — .env files on disk
- GitLab authentication via personal access token (HTTPS, not SSH)
- Claude Code CLI authentication via interactive `claude login` (one-time OAuth, stored in ~/.claude/)
- systemd service loads bot .env; mic_transformer .env available when Claude Code runs in that directory

### Slack Bot Identity
- Bot name: **SuperBot**
- Channel: single channel only, configured via environment variable (decided at deploy time)
- Tone: minimal and professional — short status updates, results only, no personality
- On task received: add emoji reaction to the message AND post "Working on it." thread reply
- Error reporting: summary + key details (error message plus relevant context like file, line, command) — no full stack traces
- Completion messages include: what was done, files changed, links (MR/branch), duration
- Unauthorized users: silent ignore — bot appears offline to them
- User allowlist: ALLOWED_USERS env var with comma-separated Slack user IDs

### Slash Commands
- `/status` — visible to all in channel, shows: current task, last 3-5 completed tasks, uptime/health, queue
- `/cancel` — visible to all, shows what's running and asks "Are you sure?" before killing
- `/help` — visible to all, shows what the bot can do and available commands

### Claude's Discretion
- Progress update strategy (edit one message vs post new replies) — Claude picks based on Slack rate limits
- Exact systemd unit file configuration
- Terraform module structure
- Startup script implementation details
- Event deduplication mechanism (in-memory vs file-based)

</decisions>

<specifics>
## Specific Ideas

- Bot should feel like a quiet, reliable tool — not a chatbot with personality
- Completion messages should be scannable — Nicole should be able to glance at it and know what happened
- The /status output is the "dashboard" — make it information-dense since there's no web UI

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-vm-and-slack-bridge*
*Context gathered: 2026-03-18*
