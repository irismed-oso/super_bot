# Requirements: Super Bot

**Defined:** 2026-03-18
**Core Value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

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
- [ ] **AGNT-02**: Full Slack thread context is passed to Claude Code session (not just the @mention message)
- [ ] **AGNT-03**: Progress updates posted to Slack thread as Claude Code works (started, key steps, done)
- [ ] **AGNT-04**: Completion summary posted to thread with what was done, files changed, and outcomes
- [ ] **AGNT-05**: Error reporting: failures posted to Slack thread with error details and context
- [x] **AGNT-06**: Process-level timeout kills hung Claude Code sessions and notifies Slack
- [x] **AGNT-07**: Max-turns limit prevents runaway sessions from consuming excessive tokens
- [x] **AGNT-08**: Persistent session continuity: thread-to-session mapping so follow-up messages in a thread continue the same Claude session
- [ ] **AGNT-09**: CLAUDE.md project memory: bot maintains persistent awareness of mic_transformer across conversations

### Git & Code Operations

- [ ] **GITC-01**: Bot can create branches, commit changes, and push to GitLab
- [ ] **GITC-02**: Bot can create merge requests on GitLab from Slack requests
- [ ] **GITC-03**: Bot can read, search, and answer questions about the mic_transformer codebase
- [ ] **GITC-04**: Bot automatically runs pytest after code changes and reports results in Slack thread
- [ ] **GITC-05**: Each task runs in an isolated git worktree to prevent concurrent task conflicts

### Operations

- [ ] **OPER-01**: Bot can execute shell commands and Python scripts on the VM
- [ ] **OPER-02**: Bot can trigger and monitor Prefect flow runs
- [ ] **OPER-03**: Bot can trigger deployments to environments from Slack
- [ ] **OPER-04**: Daily activity digest posted to channel summarizing what the bot did

## v2 Requirements

### Enhanced Safety

- **SAFE-01**: Configurable per-command approval gates (opt-in for high-risk operations)
- **SAFE-02**: Audit log of all bot actions searchable by date/user/type

### Multi-Repo

- **MULT-01**: Support for additional repos beyond mic_transformer
- **MULT-02**: Repo selection via Slack message context

### Advanced Concurrency

- **CONC-01**: Full task queue with priority ordering
- **CONC-02**: Multiple simultaneous tasks across different worktrees

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI or dashboard | Slack is the interface — no separate UI to build or maintain |
| DM-based interaction | Channel mentions only for team visibility and transparency |
| Mobile app | Slack mobile already provides access |
| Multi-repo support (v1) | mic_transformer only — pin scope for initial release |
| Per-user sandboxed environments | Unnecessary for 2-4 person team |
| Token-by-token streaming to Slack | Rate limits will get the bot throttled/banned |
| General chat assistant mode | Scoped to coding and operations on mic_transformer |
| Webhook-based auto-retry | Report failures; let humans decide to retry |

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
| AGNT-03 | Phase 3 | Pending |
| AGNT-04 | Phase 3 | Pending |
| AGNT-05 | Phase 3 | Pending |
| GITC-01 | Phase 3 | Pending |
| GITC-02 | Phase 3 | Pending |
| GITC-03 | Phase 3 | Pending |
| GITC-04 | Phase 3 | Pending |
| GITC-05 | Phase 3 | Pending |
| AGNT-09 | Phase 4 | Pending |
| OPER-01 | Phase 4 | Pending |
| OPER-02 | Phase 4 | Pending |
| OPER-03 | Phase 4 | Pending |
| OPER-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0

---
*Requirements defined: 2026-03-18*
*Last updated: 2026-03-19 after Phase 2 completion*
