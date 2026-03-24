# Roadmap: Super Bot

## Overview

Super Bot is built in four architecture-dictated phases. Phase 1 establishes the GCP VM and a correct Slack bridge — the lazy listener, event deduplication, credential isolation, and access control must be correct from the first deployed version and cannot be retrofitted. Phase 2 builds and validates the Claude Agent SDK layer in isolation, making it debuggable before connecting it to Slack. Phase 3 wires the two layers together to deliver the end-to-end MVP: @mention → Claude Code session → Slack reply, with git and PR operations. Phase 4 adds the operational differentiators — persistent project memory, script execution, Prefect flow triggering, and deployment capability — that elevate the bot beyond a basic bridge.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: VM and Slack Bridge** - GCP VM provisioned, systemd service running, Slack bot live with access control, event deduplication, and correct lazy listener pattern
- [x] **Phase 2: Agent SDK Standalone** - Claude Agent SDK invocable in isolation with session management, serialization, and timeout handling — verified before connecting to Slack
- [ ] **Phase 3: End-to-End Integration** - @mention triggers real Claude Code session, progress posted to thread, git operations and PR creation working end-to-end
- [ ] **Phase 4: Operational Hardening** - Persistent CLAUDE.md project memory, shell/script execution, Prefect flow triggering, deployment capability, and daily digest
- [x] **Phase 5: VM Validation and MCP Wiring** - mic-transformer MCP server wired into SuperBot as stdio subprocess with all VM prerequisites validated and one confirmed working tool call (completed 2026-03-23)
- [x] **Phase 6: Read-Only Status and Storage Tools** - All read-only MCP tools verified working through Slack -- status checks, storage browsing, pipeline audits, and credential pathway validation (completed 2026-03-23)
- [x] **Phase 7: Mutation Tools** - All write/trigger MCP tools verified working through Slack — extraction, reduction, posting, ingestion, sync, and benefits operations (6/8 tools working, 2 blocked by SSH; completed 2026-03-23)
- [x] **Phase 8: Response Timing** - Bot's final Slack replies show elapsed time so the team sees how long each task took (completed 2026-03-24)
- [x] **Phase 9: Git Activity Logging** - Bot captures commit, PR, and file-change data during sessions into a persistent activity log (completed 2026-03-24)
- [ ] **Phase 10: Digest Changelog** - Daily digest includes a changelog section with commits and PRs grouped by repository, with git-log verification
- [x] **Phase 11: Fast-Path Crawl and Status** - Nicole can trigger single-location EyeMed crawls and filtered status queries via pattern-matched commands that bypass the agent pipeline and respond in-place (completed 2026-03-24)
- [x] **Phase 12: Background Tasks and Batch Crawl** - Nicole can trigger a full batch crawl across all sites and get progress updates without blocking the agent queue or hitting timeouts (completed 2026-03-24)
- [ ] **Phase 13: Error UX** - Timeout and error messages give Nicole enough context to know what happened and what to do next, including live status queries

## Phase Details

### Phase 1: VM and Slack Bridge
**Goal**: The GCP infrastructure is live and the Slack bridge is deployed correctly — security, access control, and Slack event handling patterns are correct from the first version
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, SLCK-01, SLCK-02, SLCK-03, SLCK-04, SLCK-05, SLCK-06, SLCK-07, SLCK-08
**Success Criteria** (what must be TRUE):
  1. A GCP VM runs a systemd-managed bot service that survives crashes and VM reboots with journald logs accessible
  2. The bot responds to @mentions from Nicole and Han in the designated channel but silently ignores messages from unauthorized users
  3. The bot acknowledges @mentions within 3 seconds (Slack sees no timeout) even when processing takes longer
  4. Sending the same Slack event twice (simulated retry) does not trigger duplicate bot responses
  5. The bot never responds to its own messages, and /status and /cancel slash commands return a valid response in the channel
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Terraform GCP VM + startup.sh bootstrap script
- [x] 01-02-PLAN.md — Bot Python foundations (config, access control, deduplication, task state, formatter)
- [x] 01-03-PLAN.md — App entry point, handlers (lazy listener, slash commands), systemd service, Slack manifest
- [x] 01-04-PLAN.md — Deployment runbook (DEPLOY.md) + live bot verification checkpoint

### Phase 2: Agent SDK Standalone
**Goal**: The Claude Agent SDK can be invoked from a standalone Python script on the VM, with session resumption, concurrent request serialization, and timeout handling — validated in isolation before Slack wires to it
**Depends on**: Phase 1
**Requirements**: AGNT-01, AGNT-02, AGNT-06, AGNT-07, AGNT-08
**Success Criteria** (what must be TRUE):
  1. Running the standalone agent script with a natural-language request produces a real Claude Code response operating in the mic_transformer working directory
  2. A second invocation with the same thread identifier resumes the prior Claude session (not a new session), with access to prior context
  3. Two simultaneous invocations execute sequentially rather than concurrently, with the second waiting for the first to finish
  4. A deliberately hung or overlong session is killed after the configured timeout and returns a clear error rather than hanging indefinitely
  5. A session hitting the max-turns limit terminates cleanly with a report of what was completed, not a crash
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Session map persistence (session_map.py) + Agent SDK wrapper with timeout (agent.py, requirements.txt)
- [x] 02-02-PLAN.md — FIFO queue manager with cancel support (queue_manager.py) + task_state/formatter queue extensions
- [x] 02-03-PLAN.md — CLI test harness (scripts/test_agent.py) + end-to-end VM validation checkpoint

### Phase 3: End-to-End Integration
**Goal**: @mentions in Slack trigger real Claude Code sessions that can read, modify, and commit code, create MRs, run tests, and report outcomes back to the Slack thread
**Depends on**: Phase 2
**Requirements**: AGNT-03, AGNT-04, AGNT-05, GITC-01, GITC-02, GITC-03, GITC-04, GITC-05
**Success Criteria** (what must be TRUE):
  1. When Nicole sends a task @mention, the thread receives a "started" update within seconds and a completion summary when Claude finishes — no silent processing
  2. When a task fails (Claude error, git failure, test failure), the thread receives an error message with enough context to understand what went wrong
  3. Nicole can ask the bot to make a code change and receive a GitLab MR link in the Slack thread pointing to a real branch with the change committed
  4. After a code change, the bot automatically runs pytest and posts the pass/fail result to the thread without being asked
  5. Each task operates in its own isolated git worktree so a second @mention while a task is running does not corrupt the first task's working state
**Plans**: 5 plans

Plans:
- [x] 03-01-PLAN.md — gh CLI install script (scripts/setup_glab.sh) + DEPLOY.md Phase 3 section + VM verification checkpoint
- [x] 03-02-PLAN.md — Worktree lifecycle module (bot/worktree.py) + agent cwd param + QueuedTask cwd field
- [x] 03-03-PLAN.md — Progress module (bot/progress.py) + formatter extensions (format_mr_link, format_test_result)
- [x] 03-04-PLAN.md — Handler wiring: replace _run_agent_stub with _run_agent_real + on_message threading
- [ ] 03-05-PLAN.md — Deploy Phase 3 to VM + end-to-end Slack verification checkpoint

### Phase 4: Operational Hardening
**Goal**: The bot has persistent project awareness, can execute operational tasks (scripts, Prefect flows, deployments), and posts a daily activity summary — the full intended operational capability
**Depends on**: Phase 3
**Requirements**: AGNT-09, OPER-01, OPER-02, OPER-03, OPER-04
**Success Criteria** (what must be TRUE):
  1. The bot answers questions about mic_transformer without needing context re-explained — CLAUDE.md project memory is populated and active across sessions
  2. Nicole can ask the bot to run a specific Python script or shell command on the VM and receive the output in the Slack thread
  3. Nicole can ask the bot to trigger a named Prefect flow and receive confirmation of the run start and final status in the thread
  4. Nicole can ask the bot to deploy to a named environment and the deployment executes from the VM with results posted to Slack
  5. A daily summary of bot activity (tasks run, outcomes, files changed) appears in the channel each morning without manual prompting

### v1.1: Capability Parity
**Goal**: SuperBot reaches capability parity with local Claude Code for operational queries and workflows — Linear MCP, Sentry MCP, multi-repo access, and custom skills
**Depends on**: Phase 3
**Requirements**: (new) MCP-01, MCP-02, MULT-01, SKIL-01
**Success Criteria** (what must be TRUE):
  1. Asking "what's the status on eyemed all location prep?" returns real Linear issue data
  2. Bot can query Sentry for error data when troubleshooting
  3. Bot can read and answer questions about all 4 IrisMed repos (not just mic_transformer)
  4. Custom operational skills (eyemed-crawl, audit-sync, etc.) are executable via Slack

**Code changes**:
- [x] config.py — LINEAR_API_KEY, SENTRY_AUTH_TOKEN, ADDITIONAL_REPOS env vars
- [x] bot/agent.py — _build_mcp_servers(), _build_add_dirs(), wire into ClaudeAgentOptions
- [x] terraform/startup.sh — Placeholder env vars for v1.1
- [x] DEPLOY.md — v1.1 setup section with repo clone, env var, and skill deployment steps
- [ ] VM deployment — Clone repos, populate env vars, deploy skills, restart service

---

## v1.2: MCP Parity

**Milestone Goal:** SuperBot has direct access to all mic-transformer MCP tools locally on the VM, giving Nicole the same operational capabilities through Slack that local Claude Code has.

### Phase 5: VM Validation and MCP Wiring
**Goal**: The mic-transformer MCP server is wired into SuperBot as a stdio subprocess with all VM prerequisites validated — one confirmed round-trip tool call proves end-to-end connectivity
**Depends on**: v1.1
**Requirements**: MCPW-01, MCPW-02, MCPW-03, VMEV-01, VMEV-02, VMEV-03
**Success Criteria** (what must be TRUE):
  1. Sending "check deploy version" to Slack triggers the MCP `deploy_version` tool and returns the real production API version number in the thread
  2. The MCP server process starts within 60 seconds on the VM (verified by cold-start benchmark) and does not cause session timeout
  3. The mic-transformer MCP server can be disabled via the MIC_TRANSFORMER_MCP_DISABLED config flag without affecting other MCP servers (Linear, Sentry)
  4. The systemd environment file passes validation (no export prefix, no shell interpolation) and all credential config files are present on the VM
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — Feature flag (MIC_TRANSFORMER_MCP_DISABLED) + deploy script (deploy_v1.2_phase5.sh)
- [x] 05-02-PLAN.md — DEPLOY.md v1.2 section + VM deployment and end-to-end Slack verification checkpoint

### Phase 6: Read-Only Status and Storage Tools
**Goal**: Nicole can query all pipeline status, storage contents, and audit data through Slack — every read-only MCP tool returns real data, validating all four credential pathways (GCS, S3, Google Drive, PostgreSQL)
**Depends on**: Phase 5
**Requirements**: RDTL-01, RDTL-02, RDTL-03, RDTL-04, RDTL-05, RDTL-06, RDTL-07, RDTL-08
**Success Criteria** (what must be TRUE):
  1. User can ask "what's the VSP status for today?" and receive real processing status data pulled from GCS and the database
  2. User can ask "list the EyeMed remits in S3" or "show AIOUT files in GCS" and receive actual file listings
  3. User can ask "run a pipeline audit" and receive a cross-system health report covering pipeline stages, Prefect flows, and Azure mirror freshness
  4. User can ask about Google Drive folder contents, crawler locations, and IVT ingestion health and receive real data from each respective system
  5. At least one tool from each credential category (GCS, S3, Google Drive, PostgreSQL) returns valid data, confirming all credential pathways work under systemd
**Plans**: 2 plans

Plans:
- [x] 06-01-PLAN.md — Core credential pathway validation (GCS, S3, PostgreSQL): vsp_status, eyemed_status, list_gcs_aiout, list_s3_remits, pipeline_audit
- [x] 06-02-PLAN.md — Extended credential pathway validation (SSH, GDrive, secondary DBs): azure_mirror_audit, ivt_ingestion_audit, check_prefect_flow_status, gdrive_audit, list_crawler_locations

### Phase 7: Mutation Tools
**Goal**: Nicole can trigger the full daily pipeline workflow from Slack — extraction, reduction, posting prep, ingestion, sync, and benefits operations all execute through MCP tools
**Depends on**: Phase 6
**Requirements**: MTTL-01, MTTL-02, MTTL-03, MTTL-04, MTTL-05, MTTL-06, MTTL-07, MTTL-08
**Success Criteria** (what must be TRUE):
  1. User can trigger VSP or EyeMed Gemini extraction from Slack and receive confirmation that the extraction job was dispatched
  2. User can trigger AIOUT reduction from Slack and receive the reduction result or job status
  3. User can trigger autopost with dry_run default from Slack and receive the dry-run report showing what would be posted
  4. User can trigger posting prep, manual PDF ingestion, Azure mirror sync, and benefits fetch from Slack and receive confirmation or results for each
  5. User can requeue missing extraction pages from Slack and receive confirmation of which pages were requeued
**Plans**: 2 plans

Plans:
- [x] 07-01-PLAN.md — Validate API-triggered mutation tools (extraction, reduction, ingestion, requeue)
- [x] 07-02-PLAN.md — Validate subprocess/Prefect mutation tools (autopost dry_run, posting prep, Azure mirror sync, benefits fetch)

---

## v1.3: Response Timing

**Milestone Goal:** The team has visibility into how long each bot task takes, with elapsed time displayed in every completion and error message.

### Phase 8: Response Timing
**Goal**: Every bot reply includes elapsed time so the team can see how long tasks take without checking logs or timestamps
**Depends on**: Phase 7
**Requirements**: TMG-01, TMG-02
**Success Criteria** (what must be TRUE):
  1. When a task completes successfully, the bot's final Slack message includes a human-readable elapsed time footer (e.g. "Completed in 2m 34s")
  2. When a task fails or times out, the bot's error message also includes elapsed time so the team knows how long it ran before failing
  3. The elapsed time is accurate to within a few seconds of the actual wall-clock duration from @mention to final reply
**Plans**: 1 plan

Plans:
- [x] 08-01-PLAN.md — Add elapsed time footer to completion and error messages

---

## v1.4: Digest Changelog

**Milestone Goal:** The daily digest shows a changelog of git commits and PRs the bot created, so the team sees what actually changed each day.

### Phase 9: Git Activity Logging
**Goal**: The bot captures every commit, PR, and file change it produces during sessions into a persistent activity log that downstream consumers (digest, audits) can query
**Depends on**: Phase 8
**Requirements**: GITLOG-01, GITLOG-02, GITLOG-03
**Success Criteria** (what must be TRUE):
  1. After the bot commits code during a session, the commit hash, message, repo name, and branch are recorded in the activity log
  2. After the bot creates a PR during a session, the PR URL, title, and repo name are recorded in the activity log
  3. After the bot commits code, the list of files changed in that commit is recorded alongside the commit entry
  4. Activity log entries persist across bot restarts and are queryable by date
**Plans**: 1 plan

Plans:
- [ ] 09-01-PLAN.md — Post-session git activity capture (commits, PRs, file changes) into JSONL activity log

### Phase 10: Digest Changelog
**Goal**: The daily digest includes a changelog section that shows what the bot built and shipped, with commits and PRs grouped by repository and verified against git history
**Depends on**: Phase 9
**Requirements**: DGCL-01, DGCL-02, DGCL-03
**Success Criteria** (what must be TRUE):
  1. The daily digest message in Slack contains a "Changelog" section listing commits and PRs the bot created that day
  2. Changelog entries are visually grouped by repository so the team can see which repo each change landed in
  3. If session logging missed any bot commits (e.g., due to a crash), the digest still includes them because it cross-checks git log at build time
  4. When the bot had no git activity for the day, the changelog section is either absent or shows "No changes" rather than displaying stale data
**Plans**: TBD

Plans:
- [ ] 10-01: TBD

---

## v1.5: Nicole-Ready Operations

**Milestone Goal:** Nicole can check status, trigger crawls (single or batch), and get clear feedback — all without hitting timeouts or confusing error messages.

### Phase 11: Fast-Path Crawl and Status
**Goal**: Nicole can trigger a single-location EyeMed crawl or run a filtered status query with a natural-language command that resolves in seconds — no agent pipeline overhead, result edited in-place into the "Working on it." message
**Depends on**: Phase 8
**Requirements**: FAST-01, FAST-02, FAST-04
**Success Criteria** (what must be TRUE):
  1. Nicole types "crawl eyemed DME 03.20" and the bot pattern-matches it, posts "Working on it.", triggers the `eyemed-crawler-dme-manual` Prefect deployment via API, and edits the message in-place with a confirmation (run ID, location, date) — all within 5 seconds, no agent session started
  2. Nicole types "status on DME eyemed 03.16 to today" and the bot runs the status script directly with the location and date filters, then edits the "Working on it." message in-place with the results
  3. Both fast-path commands complete and update the Slack message before any agent session would even initialize, visibly faster than a standard @mention
  4. Unrecognized commands still fall through to the agent pipeline — fast-path matching does not intercept general requests
**Plans**: 1 plan

Plans:
- [x] 11-01-PLAN.md — Prefect API client + crawl handler + improved status location parsing

### Phase 12: Background Tasks and Batch Crawl
**Goal**: Nicole can say "crawl all sites for 03.20" and the bot triggers every EyeMed crawler deployment in parallel via the Prefect API, then tracks and reports progress without blocking the agent queue or timing out
**Depends on**: Phase 11
**Requirements**: FAST-03, BGTK-01, BGTK-02, BGTK-03, BGTK-04
**Success Criteria** (what must be TRUE):
  1. Nicole types "crawl all sites for 03.20" and the bot triggers all EyeMed Prefect manual deployments in parallel, posting a confirmation with how many locations were queued — the bot's response arrives in under 10 seconds regardless of how many locations there are
  2. While crawls are running, the bot posts a progress update to the thread every 2-3 minutes showing which locations finished, which are still running, and any errors — without Nicole having to ask
  3. A separate agent task (e.g., a code question) submitted while a batch crawl is in progress executes normally — the background polling does not occupy the agent queue
  4. When all crawl runs finish, the bot posts a final summary showing per-location outcomes: files found, no disbursement, or error with message
**Plans**: 1 plan

Plans:
- [ ] 12-01-PLAN.md — Batch crawl trigger with parallel Prefect API + background progress monitor

### Phase 13: Error UX
**Goal**: When something goes wrong or takes too long, Nicole sees a message that tells her what was attempted, what the current state is, and what to do next — never a bare timeout or generic error
**Depends on**: Phase 11
**Requirements**: ERUX-01, ERUX-02, ERUX-03
**Success Criteria** (what must be TRUE):
  1. When a task times out, the bot's message names what was being attempted (e.g., "was running: crawl eyemed DME") and suggests a concrete next action (e.g., "check status with: status on DME eyemed today")
  2. The timeout message is visually distinct from a hard failure message — Nicole can tell at a glance whether the task timed out, failed outright, or is still running in the background
  3. When Nicole sends "are you broken?" or "are you still going?", the bot pattern-matches it as a status query and replies with the actual current task state (idle, running, what it's doing) instead of spawning a new agent session
**Plans**: 1 plan

Plans:
- [ ] 13-01-PLAN.md — Contextual error messages, visual error distinction, and fast-path bot status query

---

## Progress

**Execution Order:**
Phases execute in order: 1 -> 2 -> 3 -> 4 -> v1.1 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 -> 13

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. VM and Slack Bridge | v1.0 | 4/4 | Complete | 2026-03-19 |
| 2. Agent SDK Standalone | v1.0 | 3/3 | Complete | 2026-03-20 |
| 3. End-to-End Integration | v1.0 | 4/5 | In progress | - |
| 4. Operational Hardening | v1.0 | 0/TBD | Not started | - |
| v1.1 Capability Parity | v1.1 | 1/TBD | In progress | - |
| 5. VM Validation and MCP Wiring | v1.2 | 2/2 | Complete | 2026-03-23 |
| 6. Read-Only Status and Storage Tools | v1.2 | 2/2 | Complete | 2026-03-23 |
| 7. Mutation Tools | v1.2 | 2/2 | Complete | 2026-03-23 |
| 8. Response Timing | v1.3 | 1/1 | Complete | 2026-03-24 |
| 9. Git Activity Logging | v1.4 | Complete    | 2026-03-24 | - |
| 10. Digest Changelog | v1.4 | 0/TBD | Not started | - |
| 11. Fast-Path Crawl and Status | v1.5 | 1/1 | Complete | 2026-03-24 |
| 12. Background Tasks and Batch Crawl | 1/1 | Complete    | 2026-03-24 | - |
| 13. Error UX | v1.5 | 0/TBD | Not started | - |
