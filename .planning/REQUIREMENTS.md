# Requirements: Super Bot

**Defined:** 2026-03-18
**Core Value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.

## v1.0 Requirements (Complete)

### Infrastructure

- [x] **INFRA-01**: GCP VM provisioned with dedicated low-privilege bot user (not root)
- [x] **INFRA-02**: mic_transformer repository cloned on VM with full Python environment and dependencies
- [x] **INFRA-03**: Claude Code CLI installed and authenticated with Anthropic API key on the VM
- [x] **INFRA-04**: systemd service configured for auto-restart with journald logging
- [x] **INFRA-05**: Credentials stored securely in .env files with chmod 600, owned by dedicated bot user
- [x] **INFRA-06**: GitLab SSH key or token configured on VM for push/MR operations

### Slack Integration

- [x] **SLCK-01**: Slack bot app created with Socket Mode (outbound WebSocket, no public URL)
- [x] **SLCK-02**: Bot responds to @mentions in a designated team channel
- [x] **SLCK-03**: Named-user allowlist restricts who can trigger the bot (Nicole, Han, named users)
- [x] **SLCK-04**: Bot filters its own messages to prevent infinite response loops
- [x] **SLCK-05**: Lazy listener pattern: ACK within 3 seconds, process asynchronously
- [x] **SLCK-06**: Event deduplication prevents duplicate task execution on Slack retries
- [x] **SLCK-07**: /sb-status slash command shows currently running task and recent history (/status is Slack reserved)
- [x] **SLCK-08**: /cancel slash command stops an in-flight Claude Code session

### Agent Core

- [x] **AGNT-01**: Claude Agent SDK bridges Slack messages to Claude Code sessions running in mic_transformer directory
- [x] **AGNT-02**: Full Slack thread context is passed to Claude Code session (not just the @mention message)
- [x] **AGNT-03**: Progress updates posted to Slack thread as Claude Code works (started, key steps, done)
- [x] **AGNT-04**: Completion summary posted to thread with what was done, files changed, and outcomes
- [x] **AGNT-05**: Error reporting: failures posted to Slack thread with error details and context
- [x] **AGNT-06**: Process-level timeout kills hung Claude Code sessions and notifies Slack
- [x] **AGNT-07**: Max-turns limit prevents runaway sessions from consuming excessive tokens
- [x] **AGNT-08**: Persistent session continuity: thread-to-session mapping so follow-up messages in a thread continue the same Claude session
- [x] **AGNT-09**: CLAUDE.md project memory: bot maintains persistent awareness of mic_transformer across conversations

### Git & Code Operations

- [x] **GITC-01**: Bot can create branches, commit changes, and push to GitLab
- [x] **GITC-02**: Bot can create merge requests on GitHub from Slack requests
- [x] **GITC-03**: Bot can read, search, and answer questions about the mic_transformer codebase
- [x] **GITC-04**: Bot automatically runs pytest after code changes and reports results in Slack thread
- [x] **GITC-05**: Each task runs in an isolated git worktree to prevent concurrent task conflicts

### Operations

- [x] **OPER-01**: Bot can execute shell commands and Python scripts on the VM
- [x] **OPER-02**: Bot can trigger and monitor Prefect flow runs
- [x] **OPER-03**: Bot can trigger deployments to environments from Slack
- [x] **OPER-04**: Daily activity digest posted to channel summarizing what the bot did

## v1.1 Requirements (Complete)

### MCP & Multi-Repo

- [x] **MCP-01**: Linear MCP server wired into Claude Agent SDK sessions
- [x] **MCP-02**: Sentry MCP server wired into Claude Agent SDK sessions
- [x] **MULT-01**: Bot can read and answer questions about all 4 IrisMed repos
- [x] **SKIL-01**: Custom operational skills executable via Slack

## v1.2 Requirements

Requirements for MCP Parity milestone. Each maps to roadmap phases.

### MCP Wiring

- [x] **MCPW-01**: mic-transformer MCP server added to _build_mcp_servers() in agent.py as stdio subprocess
- [x] **MCPW-02**: MIC_TRANSFORMER_MCP_ENABLED config flag controls whether mic-transformer MCP server is wired
- [x] **MCPW-03**: mcp[cli]~=1.26.0 installed in mic_transformer .venv on VM

### VM Environment

- [x] **VMEV-01**: mic_transformer config/*.yml credential files present and valid on VM
- [x] **VMEV-02**: systemd EnvironmentFile syntax validated (no export, no interpolation)
- [x] **VMEV-03**: MCP server cold-start completes within 60-second SDK timeout on VM hardware

### Read-Only Tools

- [x] **RDTL-01**: User can check VSP/EyeMed processing status via Slack
- [x] **RDTL-02**: User can browse S3 remits and GCS AIOUT files via Slack
- [x] **RDTL-03**: User can check full pipeline status and run pipeline audit via Slack
- [x] **RDTL-04**: User can check Azure mirror data freshness and run status via Slack
- [x] **RDTL-05**: User can audit IVT data ingestion health via Slack
- [x] **RDTL-06**: User can check Prefect flow status and get logs via Slack
- [x] **RDTL-07**: User can audit Google Drive folders via Slack
- [x] **RDTL-08**: User can list crawler locations via Slack

### Mutation Tools

- [x] **MTTL-01**: User can trigger VSP/EyeMed Gemini extraction via Slack
- [x] **MTTL-02**: User can trigger AIOUT reduction via Slack
- [x] **MTTL-03**: User can trigger autopost (with dry_run default) via Slack
- [x] **MTTL-04**: User can trigger posting prep and GDrive upload via Slack
- [x] **MTTL-05**: User can ingest manual PDFs into the pipeline via Slack
- [x] **MTTL-06**: User can trigger Azure mirror sync via Slack
- [ ] **MTTL-07**: User can fetch vision benefits via Slack (skipped: 10-min polling vs 10-min session timeout)
- [x] **MTTL-08**: User can requeue missing extraction pages via Slack

## v1.3 Requirements

Requirements for Response Timing milestone.

### Timing Display

- [x] **TMG-01**: Completion messages show elapsed time as human-readable footer (e.g. "Completed in 2m 34s")
- [x] **TMG-02**: Error/timeout messages also show elapsed time

## Future Requirements

### Crawler

- **CRWL-01**: User can trigger VSP/EyeMed portal crawlers via Slack (requires Chrome on VM)

### Enhanced Safety

- **SAFE-01**: Configurable per-command approval gates (opt-in for high-risk operations)
- **SAFE-02**: Audit log of all bot actions searchable by date/user/type

### Advanced Concurrency

- **CONC-01**: Full task queue with priority ordering
- **CONC-02**: Multiple simultaneous tasks across different worktrees

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI or dashboard | Slack is the interface — no separate UI to build or maintain |
| DM-based interaction | Channel mentions only for team visibility and transparency |
| Crawler tools (v1.2) | Requires Chrome/Chromium on VM — deferred until confirmed available |
| Flask API bridge | Direct stdio MCP is simpler and sufficient |
| Token-by-token streaming to Slack | Rate limits will get the bot throttled/banned |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Complete |
| INFRA-06 | Phase 1 | Complete |
| SLCK-01 | Phase 1 | Complete |
| SLCK-02 | Phase 1 | Complete |
| SLCK-03 | Phase 1 | Complete |
| SLCK-04 | Phase 1 | Complete |
| SLCK-05 | Phase 1 | Complete |
| SLCK-06 | Phase 1 | Complete |
| SLCK-07 | Phase 1 | Complete |
| SLCK-08 | Phase 1 | Complete |
| AGNT-01 | Phase 2 | Complete |
| AGNT-02 | Phase 2 | Complete |
| AGNT-06 | Phase 2 | Complete |
| AGNT-07 | Phase 2 | Complete |
| AGNT-08 | Phase 2 | Complete |
| AGNT-03 | Phase 3 | Complete |
| AGNT-04 | Phase 3 | Complete |
| AGNT-05 | Phase 3 | Complete |
| GITC-01 | Phase 3 | Complete |
| GITC-02 | Phase 3 | Complete |
| GITC-03 | Phase 3 | Complete |
| GITC-04 | Phase 3 | Complete |
| GITC-05 | Phase 3 | Complete |
| AGNT-09 | Phase 4 | Complete |
| OPER-01 | Phase 4 | Complete |
| OPER-02 | Phase 4 | Complete |
| OPER-03 | Phase 4 | Complete |
| OPER-04 | Phase 4 | Complete |
| MCP-01 | v1.1 | Complete |
| MCP-02 | v1.1 | Complete |
| MULT-01 | v1.1 | Complete |
| SKIL-01 | v1.1 | Complete |
| MCPW-01 | Phase 5 | Complete |
| MCPW-02 | Phase 5 | Complete |
| MCPW-03 | Phase 5 | Complete |
| VMEV-01 | Phase 5 | Complete |
| VMEV-02 | Phase 5 | Complete |
| VMEV-03 | Phase 5 | Complete |
| RDTL-01 | Phase 6 | Complete |
| RDTL-02 | Phase 6 | Complete |
| RDTL-03 | Phase 6 | Complete |
| RDTL-04 | Phase 6 | Complete |
| RDTL-05 | Phase 6 | Complete |
| RDTL-06 | Phase 6 | Complete |
| RDTL-07 | Phase 6 | Complete |
| RDTL-08 | Phase 6 | Complete |
| MTTL-01 | Phase 7 | Complete |
| MTTL-02 | Phase 7 | Complete |
| MTTL-03 | Phase 7 | Complete |
| MTTL-04 | Phase 7 | Complete |
| MTTL-05 | Phase 7 | Complete |
| MTTL-06 | Phase 7 | Blocked (SSH) |
| MTTL-07 | Phase 7 | Blocked (SSH) |
| MTTL-08 | Phase 7 | Complete |
| TMG-01 | Phase 8 | Complete |
| TMG-02 | Phase 8 | Complete |

**Coverage:**
- v1.0 requirements: 32 total (all complete)
- v1.1 requirements: 4 total (all complete)
- v1.2 requirements: 22 total (20 complete, 2 blocked)
- v1.3 requirements: 2 total
- Mapped to phases: 2/2
- Unmapped: 0

---
*Requirements defined: 2026-03-18*
*Last updated: 2026-03-23 after v1.3 requirements defined*
