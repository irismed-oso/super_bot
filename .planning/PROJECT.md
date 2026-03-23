# Super Bot

## What This Is

A Slack-integrated Claude Code agent running on a Google Cloud VM with a clone of mic_transformer. A small team (Nicole, Han, and 1-2 others) @mentions the bot in a Slack channel, and it autonomously performs code changes, runs operations, investigates issues, and manages deployments on the mic_transformer codebase — then reports results back to Slack.

## Core Value

Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness of the project.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- GCP VM provisioned with systemd service, auto-restart, journald logging (v1.0 Phase 1)
- Slack bot with Socket Mode, lazy listener, event dedup, access control (v1.0 Phase 1)
- Claude Agent SDK with session management, timeout, queue serialization (v1.0 Phase 2)
- End-to-end: @mention triggers Claude session, progress/results posted to thread (v1.0 Phase 3)
- Git worktree isolation, branch/commit/PR operations (v1.0 Phase 3)
- Linear MCP and Sentry MCP integration (v1.1)
- Multi-repo read access (v1.1)

### Active

- [ ] mic-transformer MCP server wired into SuperBot Claude Agent SDK sessions
- [ ] All 25+ operational tools available through Slack (status, extraction, reduction, posting, crawling, etc.)
- [ ] VM environment has all mic-transformer MCP dependencies installed
- [ ] Required credentials/env vars configured on VM for MCP tools

## Current Milestone: v1.2 MCP Parity

**Goal:** SuperBot has direct access to all mic-transformer MCP tools locally on the VM, giving Nicole the same operational capabilities through Slack that local Claude Code has.

**Target features:**
- mic-transformer MCP server wired into SuperBot's Claude Agent SDK sessions as stdio subprocess
- All 13 tool modules (25+ tools) available: status, extraction, reduction, posting, storage, crawler, gdrive, ingestion, benefits, deploy, azure_mirror, ivt_ingestion, analytics
- VM mic_transformer .venv has `mcp` and `fastmcp` packages installed
- Required cloud credentials (GCS, S3, Azure, Prefect, Revolution) accessible to MCP subprocess

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
| Claude Code CLI over direct API | Native git/shell/code support, memory system, less custom code to build | — Pending |
| Full autonomy (no approval gates) | Speed matters more than caution for this internal tool; team has visibility via channel | — Pending |
| Channel mentions over DMs | Team transparency — everyone sees what's being asked and done | — Pending |
| Persistent context | Bot should build ongoing awareness of repo state and past work, not start fresh each time | — Pending |
| Flexible VM sizing | Start small, scale if needed — avoid over-provisioning | — Pending |

---
*Last updated: 2026-03-23 after milestone v1.2 started*
