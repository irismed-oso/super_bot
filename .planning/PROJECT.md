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

### Active

- [ ] Elapsed time displayed in bot's final Slack reply (e.g. "Completed in 2m 34s")

## Current Milestone: v1.3 Response Timing

**Goal:** Show how long each bot response took in the final Slack reply, so the team has visibility into task duration.

**Target features:**
- Pass elapsed duration from handler to post_result
- Append human-readable elapsed time footer to completion and error messages

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

---
*Last updated: 2026-03-23 after milestone v1.3 started*
