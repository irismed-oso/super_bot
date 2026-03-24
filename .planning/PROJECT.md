# Super Bot

## What This Is

A Slack-integrated Claude Code agent running on a Google Cloud VM with a clone of mic_transformer. A small team (Nicole, Han, and 1-2 others) @mentions the bot in a Slack channel, and it autonomously performs code changes, runs operations, investigates issues, and manages deployments on the mic_transformer codebase — then reports results back to Slack.

## Core Value

Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness of the project.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- GCP VM provisioned with systemd service, auto-restart, journald logging -- v1.0
- Slack bot with Socket Mode, lazy listener, event dedup, access control -- v1.0
- Claude Agent SDK with session management, timeout, queue serialization -- v1.0
- End-to-end: @mention triggers Claude session, progress/results posted to thread -- v1.0
- Git worktree isolation, branch/commit/PR operations -- v1.0
- Linear MCP and Sentry MCP integration -- v1.1
- Multi-repo read access (all 4 IrisMed repos) -- v1.1
- Custom operational skills via Slack -- v1.1
- Daily activity digest -- v1.1
- mic-transformer MCP server (35+ tools) wired as stdio subprocess -- v1.2
- All credential pathways validated: GCS, S3, PostgreSQL (x3), Google Drive, SSH -- v1.2
- Read-only ops: VSP/EyeMed status, pipeline audit, Azure mirror, IVT health, GDrive audit -- v1.2
- Mutation ops: extraction, reduction, autopost (dry_run), posting prep, PDF ingestion, Azure sync -- v1.2
- Elapsed time displayed in bot's final Slack reply -- v1.3
- Fast-path command system bypassing agent pipeline for common queries -- v1.3
- EyeMed scan status script for instant lookback queries -- v1.3
- Multi-channel support -- v1.3
- Timeout partial text preservation -- v1.3
- Crawler exit code fix (distinct codes for success/error/no-files) -- v1.3
- Daily digest changelog with git commits and PRs grouped by repo -- v1.4
- Git log cross-check at digest time catches missed commits (crash recovery) -- v1.4
- Fast-path crawl triggering via Prefect API (single location + batch) -- v1.5
- Fast-path status with location/date filters -- v1.5
- Background task support for long-running operations -- v1.5
- Better error/timeout messages with suggested next actions -- v1.5

### Active

- [ ] Periodic progress heartbeat every 5 minutes during long sessions
- [ ] Progress message shows last activity, turn count, and elapsed time

## Current Milestone: v1.6 Progress Heartbeat

**Goal:** During long-running sessions (up to 30 min), the bot posts periodic progress updates every 5 minutes by editing a single message — so users always know it's still working.

**Target features:**
- Periodic heartbeat timer that fires every 5 minutes during agent execution
- Progress message edited in-place showing: last activity + turn count + elapsed time
- Heartbeat survives silent thinking periods (no tool use required to trigger)

### Out of Scope

- Web UI or dashboard — Slack is the interface
- Multi-repo support — mic_transformer only for v1
- Approval gates for destructive actions — full autonomy by design
- DM-based interaction — channel mentions only for team visibility
- Mobile app or alternative chat platforms

## Context

- mic_transformer is an existing Python/Flask/Prefect project for insurance remittance processing, AI PDF extraction, EMR posting, and data sync
- The team already uses Slack for communication
- Inspired by OpenClaw/ZeroClaw — autonomous coding agents accessible through chat interfaces
- Claude Code CLI has native git, shell, and code editing support, making it the natural engine
- The VM needs Python environment, git, and network access to GitLab and any services mic_transformer talks to

## Constraints

- **Cloud**: Google Cloud Platform — team already uses GCP
- **Interface**: Slack only — no other UIs
- **Engine**: Claude Code CLI — not a custom API integration
- **Repo**: mic_transformer clone on the VM
- **VM Size**: Start small (e2-small/medium), resize as needed
- **Auth**: Anthropic API key on the VM for Claude Code
- **Access**: Slack channel-based, small team of named users

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Claude Code CLI over direct API | Native git/shell/code support, memory system, less custom code | Good |
| Full autonomy (no approval gates) | Speed matters for internal tool; team visibility via channel | Good |
| Channel mentions over DMs | Team transparency | Good |
| Socket Mode (no public URL) | Eliminates load balancer, TLS, ingress | Good |
| Claude Agent SDK (not subprocess) | Avoids TTY-hang bug; async, required for lazy listener | Good |
| Direct MCP stdio (not Flask bridge) | Simpler, standard pattern, SDK handles it natively | Good |
| MIC_TRANSFORMER_MCP_DISABLED flag | Enabled by default, disable override for troubleshooting | Good |
| Autopost dry_run default | Built-in safety for mutation tools | Good |
| Post-session git log (not real-time stream) | Simpler, more reliable, git log is source of truth | Good |
| Separate digest_changelog.py module | Testability, keeps daily_digest.py focused | Good |

---
*Last updated: 2026-03-24 after v1.4 milestone complete*
