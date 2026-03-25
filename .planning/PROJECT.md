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

- Progress heartbeat during long sessions (1 min first, then every 3 min) -- v1.6
- Heartbeat shows last activity, turn count, elapsed time -- v1.6
- Completion edit ("Completed in Xm Ys") before result posts -- v1.6
- Reusable deploy script (scripts/deploy.sh) with push/pull/deps/restart/health-check -- v1.7
- All v1.4-v1.6 features verified working on production VM -- v1.7

### Active

- [ ] Deploy from Slack for all 4 IrisMed repos (push, pull, deps, restart, verify)
- [ ] Git-based rollback and redeploy from Slack
- [ ] Deploy status: running version, last deploy time, changes since last deploy
- [ ] Log access via Slack: journald tail + filtered, Prefect flow logs, app logs
- [ ] Bot health dashboard: uptime, errors, current activity (fast-path)
- [ ] Pipeline status: fast-path summary + agent deep investigation
- [ ] Live smoke tests for v1.4-v1.6 features on production VM

## Current Milestone: v1.8 Production Ops

**Goal:** Full production observability and deployment control from Slack — deploy any repo, rollback, read logs, monitor bot health and pipeline status.

**Target features:**
- Deploy any of the 4 IrisMed repos from Slack with one command
- Git-based rollback to previous version + redeploy
- Deploy status showing what's running and what changed
- Log access: journald tail/filter, Prefect flow logs, application logs
- Bot health and pipeline status as fast-path commands
- Live verification of v1.4-v1.6 features (folded from v1.7 Phase 16)

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
| Fast-path regex before agent enqueue | Sub-second response for known commands | Good |
| httpx.AsyncClient for Prefect API | Native async, no thread wrapping needed | Good |
| asyncio timer heartbeat (not tool-use driven) | Fires during silent thinking phases | Good |
| finish() vs stop() for heartbeat | Completion gets final edit, cancel/error doesn't | Good |

---
*Last updated: 2026-03-25 after milestone v1.8 started*
