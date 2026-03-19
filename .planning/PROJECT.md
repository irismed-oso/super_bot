# Super Bot

## What This Is

A Slack-integrated Claude Code agent running on a Google Cloud VM with a clone of mic_transformer. A small team (Nicole, Han, and 1-2 others) @mentions the bot in a Slack channel, and it autonomously performs code changes, runs operations, investigates issues, and manages deployments on the mic_transformer codebase — then reports results back to Slack.

## Core Value

Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness of the project.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] GCP VM provisioned and configured with mic_transformer clone
- [ ] Claude Code CLI installed and authenticated on the VM
- [ ] Slack bot app created and connected to a team channel
- [ ] Slack-to-Claude bridge: incoming @mentions trigger Claude Code sessions
- [ ] Claude Code output streamed/posted back to Slack as replies
- [ ] Persistent context across conversations (Claude Code memory, project state)
- [ ] Full repo access: git operations, branch creation, PR workflows
- [ ] Script execution: run Prefect flows, Python scripts, operational tasks
- [ ] Deploy capability: push to environments from the VM
- [ ] Small team access control (Nicole, Han, named users)

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
*Last updated: 2026-03-18 after initialization*
