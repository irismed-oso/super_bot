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
- [x] **Phase 10: Digest Changelog** - Daily digest includes a changelog section with commits and PRs grouped by repository, with git-log verification (completed 2026-03-24)
- [x] **Phase 11: Fast-Path Crawl and Status** - Nicole can trigger single-location EyeMed crawls and filtered status queries via pattern-matched commands that bypass the agent pipeline and respond in-place (completed 2026-03-24)
- [x] **Phase 12: Background Tasks and Batch Crawl** - Nicole can trigger a full batch crawl across all sites and get progress updates without blocking the agent queue or hitting timeouts (completed 2026-03-24)
- [x] **Phase 13: Error UX** - Timeout and error messages give Nicole enough context to know what happened and what to do next, including live status queries (completed 2026-03-24)
- [x] **Phase 14: Progress Heartbeat** - Bot edits a single progress message every 5 minutes during long agent sessions showing last activity, turn count, and elapsed time (completed 2026-03-24)
- [x] **Phase 15: Deploy Script** - Reusable deploy script that pushes code, installs deps, restarts service, and verifies health on the production VM (completed 2026-03-25)
- [x] **Phase 16: Live Verification** - All v1.4-v1.6 features smoke-tested on the production VM -- digest changelog, fast-path commands, background tasks, heartbeat (completed 2026-03-25)
- [x] **Phase 17: Deploy Foundation** - Deploy super_bot and mic_transformer from Slack with self-restart handling, deploy status, diff preview, and active-task guard plus live verification of v1.4-v1.6 features (completed 2026-03-25)
- [x] **Phase 18: Rollback** - Git-based rollback to previous commit with health check and automatic roll-forward on failure (completed 2026-03-25)
- [x] **Phase 19: Log Access** - Tail and filter journald logs, view Prefect flow logs, with structlog parsing and Slack-safe truncation (completed 2026-03-25)
- [x] **Phase 20: Health Dashboard** - Fast-path bot health overview showing uptime, queue depth, errors, memory, version, and last restart (completed 2026-03-26)
- [x] **Phase 21: Pipeline Status** - Fast-path Prefect pipeline summary showing completed, failed, and running flow runs in the last 24 hours (completed 2026-03-26)
- [x] **Phase 22: SQLite Foundation and Memory Commands** - SQLite database with FTS5 search, memory CRUD module, and fast-path remember/recall/forget/list commands (completed 2026-03-25)
- [x] **Phase 23: Auto-Recall Injection** - Relevant memories automatically retrieved and injected into every agent session prompt with brief citation (completed 2026-03-25)
- [x] **Phase 24: Post-Session Thread Scanning** - Automatic extraction of memorable information from completed threads with task history auto-capture (completed 2026-03-25)

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
**Plans**: 1 plan

Plans:
- [ ] 10-01-PLAN.md — Changelog builder with git-log cross-check + wire into daily digest

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

## v1.6: Progress Heartbeat

**Milestone Goal:** During long-running sessions (up to 30 min), the bot posts periodic progress updates every 5 minutes by editing a single message -- so users always know it is still working.

### Phase 14: Progress Heartbeat
**Goal**: During long agent sessions, the bot edits a single progress message every 5 minutes with current status -- users never wonder whether the bot is stuck or still working
**Depends on**: Phase 13
**Requirements**: HRTB-01, HRTB-02, HRTB-03, HRTB-04
**Success Criteria** (what must be TRUE):
  1. When an agent session runs longer than 5 minutes, the bot edits its progress message in-place showing elapsed time, the last activity the agent performed, and the current turn count (e.g., "Still working... Searching codebase for payment logic | Turn 8/25 | 5m 12s elapsed")
  2. The heartbeat fires on schedule even when the agent is in a long thinking phase with no tool calls -- it does not depend on agent tool use events to trigger
  3. When the agent completes, times out, or is cancelled, the heartbeat timer stops cleanly with no further edits to the progress message after the final result is posted
  4. The progress message uses a consistent format: "Still working... [Last Activity] | Turn X/25 | Ym Zs elapsed"
**Plans**: 1 plan

Plans:
- [x] 14-01-PLAN.md — Heartbeat timer module + handler/queue lifecycle wiring

---


## v1.7: Deploy & Verify

**Milestone Goal:** Get v1.4-v1.6 features deployed and verified on the production VM with a reusable deploy script.

### Phase 15: Deploy Script
**Goal**: A single reusable script deploys any future milestone to the production VM -- push, pull, deps, restart, health check -- so deployments are repeatable and not manual SSH sessions
**Depends on**: Phase 14
**Requirements**: DPLY-01, DPLY-02
**Success Criteria** (what must be TRUE):
  1. Running the deploy script from a local machine pushes the current branch, SSHs to the VM, pulls code, installs any new Python dependencies, restarts the systemd service, and confirms the service is healthy -- all in one command
  2. The deploy script exits with a clear success/failure status and prints the service health (systemd active, no crash loops in recent journal logs)
  3. The same deploy script can be reused for the next milestone without modification (no hardcoded version numbers or one-shot logic)
  4. After the deploy script completes, the bot responds to a Slack @mention within 30 seconds, confirming it is live and functional
**Plans**: 1 plan

Plans:
- [ ] 15-01-PLAN.md — Reusable deploy script + DEPLOY.md update + VM deployment checkpoint

### Phase 16: Live Verification
**Goal**: Every feature shipped in v1.4-v1.6 is smoke-tested on the production VM -- the team confirms the bot works end-to-end in its real environment, not just locally
**Depends on**: Phase 15
**Requirements**: VRFY-01, VRFY-02, VRFY-03, VRFY-04
**Success Criteria** (what must be TRUE):
  1. The daily digest fires on the VM and includes a changelog section with any git activity from the day (or shows "No changes" cleanly when there is none) -- verifying VRFY-01
  2. Nicole can type "crawl eyemed DME [date]" and "status on DME eyemed [date range]" in the production Slack channel and receive fast-path responses edited in-place within seconds -- verifying VRFY-02
  3. Nicole can trigger a batch crawl ("crawl all sites for [date]") and observe background progress updates posting to the thread every 2-3 minutes without blocking other bot tasks -- verifying VRFY-03
  4. When a long agent session runs on the VM, the progress message is edited with heartbeat updates (last activity, turn count, elapsed time), and on completion the message shows "Completed in Xm Ys" -- verifying VRFY-04
**Plans**: 1 plan

Plans:
- [ ] 16-01-PLAN.md — Live smoke tests for all v1.4-v1.6 features

---

## v1.8: Production Ops

**Milestone Goal:** Full production observability and deployment control from Slack -- deploy any repo, rollback, read logs, monitor bot health and pipeline status. Also completes pending v1.7 live verification (VRFY-01 through VRFY-04).

### Phase 17: Deploy Foundation
**Goal**: The team can deploy super_bot and mic_transformer from Slack with a single command, see what would be deployed before deploying, and get blocked if an agent task is running -- with self-restart handling for super_bot deploys and live verification of v1.4-v1.6 features baked into the deploy workflow
**Depends on**: Phase 16
**Requirements**: SDPL-01, SDPL-02, SDPL-03, SDPL-04, SDPL-05, VRFY-01, VRFY-02, VRFY-03, VRFY-04
**Success Criteria** (what must be TRUE):
  1. Nicole types "deploy super_bot" and the bot posts "Deploying now, I'll be back shortly", restarts itself, and after restart posts an "I'm back" confirmation to the original thread with the new commit SHA
  2. Nicole types "deploy mic_transformer" and the bot pulls latest code, installs deps, and reports success or failure -- all without restarting itself
  3. Nicole types "deploy status" and sees the current commit, branch, last deploy time, and count of pending changes for each configured repo
  4. Nicole types "deploy preview super_bot" and sees the list of commits that would be deployed (between current HEAD and origin/main)
  5. If Nicole types "deploy super_bot" while an agent task is running, the bot warns about the active task and requires "deploy force super_bot" to proceed
**Plans**: 3 plans

Plans:
- [x] 17-01-PLAN.md — Deploy-state persistence, repo config, and fast-path deploy status/preview commands
- [x] 17-02-PLAN.md — Deploy execution via Prefect (self-deploy + mic_transformer polling) + app.py startup recovery
- [x] 17-03-PLAN.md — VM deployment + live verification of deploy commands and v1.4-v1.6 features
### Phase 18: Rollback
**Goal**: The team can undo a bad deploy by rolling back to the previous commit and redeploying, with automatic recovery if the rollback itself fails
**Depends on**: Phase 17
**Requirements**: RLBK-01, RLBK-02
**Success Criteria** (what must be TRUE):
  1. Nicole types "rollback super_bot" and the bot reverts to the previous commit, redeploys (with self-restart handling for super_bot), and confirms the rollback succeeded with the restored commit SHA
  2. Nicole types "rollback mic_transformer" and the bot reverts to the previous commit, reinstalls deps, and confirms the rollback succeeded
  3. If a rollback fails the post-deploy health check, the bot automatically rolls forward to the pre-rollback commit and reports that the rollback was aborted with the reason
**Plans**: 1 plan

Plans:
- [ ] 20-01-PLAN.md — Health dashboard fast-path handler with system metrics

### Phase 19: Log Access
**Goal**: The team can read service logs and Prefect flow logs from Slack without SSHing to the VM -- with output parsed and truncated to fit Slack messages
**Depends on**: Phase 17
**Requirements**: LOGS-01, LOGS-02, LOGS-03, LOGS-04
**Success Criteria** (what must be TRUE):
  1. Nicole types "logs superbot 50" and sees the last 50 lines of journald output for the superbot service, with structlog JSON parsed down to timestamp, level, and event
  2. Nicole types "logs superbot error last 1h" and sees only journald lines matching "error" from the last hour
  3. Nicole types "prefect logs [run-id]" and sees the log output for that specific Prefect flow run
  4. Log output longer than Slack's message limit is truncated with a line count indicator (e.g., "showing 20 of 150 lines") and secret-like patterns are scrubbed before posting
**Plans**: 1 plan

Plans:
- [ ] 19-01-PLAN.md — Log tools module (journald + Prefect logs) with structlog parsing, secret scrubbing, and agent wiring



### Phase 20: Health Dashboard
**Goal**: The team can see a snapshot of bot health at a glance -- uptime, queue depth, error rate, memory usage, and version -- via a fast-path command
**Depends on**: Phase 19
**Requirements**: HLTH-01
**Success Criteria** (what must be TRUE):
  1. Nicole types "bot health" and sees a formatted dashboard with uptime, queue depth, recent error count, memory usage, current git version, and last restart time
  2. The health dashboard responds in under 3 seconds as a fast-path command (no agent session)
  3. The error count reflects actual journald errors in the last 24 hours, not a static counter
**Plans**: 1 plan

Plans:
- [ ] 20-01-PLAN.md — Health dashboard fast-path handler with system metrics

### Phase 21: Pipeline Status
**Goal**: The team can see a summary of Prefect pipeline activity via the agent pipeline -- how many flows completed, failed, or are running, with natural language time windows
**Depends on**: Phase 19
**Requirements**: HLTH-02
**Success Criteria** (what must be TRUE):
  1. Nicole types "pipeline status" and sees a compact summary of Prefect flow runs in the last 24 hours, grouped by status (failed first, then running, then completed)
  2. The summary includes flow names, timestamps, and run IDs so Nicole can follow up with "prefect logs [id]"
  3. Nicole can specify time windows naturally ("pipeline status today", "pipeline status this week") and the agent interprets them
**Plans**: 1 plan

Plans:
- [ ] 21-01-PLAN.md — Pipeline status CLI tool and agent rules for Prefect flow summary

---

## v1.9: Persistent Memory

**Milestone Goal:** The bot remembers rules, facts, history, and preferences across sessions using a local SQLite database, auto-recalls relevant memories during tasks, and automatically extracts knowledge from Slack threads.

### Phase 22: SQLite Foundation and Memory Commands
**Goal**: The team can explicitly store, search, and manage bot memories through Slack commands -- the database foundation is live and the bot has immediate utility as a shared knowledge store
**Depends on**: Phase 21
**Requirements**: STOR-01, STOR-02, STOR-03, STOR-04, CMD-01, CMD-02, CMD-03, CMD-04, CMD-05
**Success Criteria** (what must be TRUE):
  1. Nicole types "remember always run autopost with dry_run first" and the bot stores it as a rule, confirms storage with the assigned category, and the memory persists across bot restarts
  2. Nicole types "recall autopost" and the bot returns relevant memories ranked by FTS5 BM25 relevance, showing content, category, who stored it, and when
  3. Nicole types "forget dry_run" and if multiple memories match, the bot lists them with IDs and asks which to delete -- a single match is deleted with confirmation
  4. Nicole types "list memories" and sees all stored memories grouped by category (rules, facts, history, preferences), with optional category filter ("list memories rules")
  5. All memory commands respond in under 2 seconds as fast-path commands -- they never spawn an agent session and do not collide with existing fast-path patterns like "crawl" or "status"
**Plans**: 2 plans

Plans:
- [ ] 22-01-PLAN.md — SQLite memory store module with FTS5 schema and async CRUD
- [ ] 22-02-PLAN.md — Memory fast-path commands (remember/recall/forget/list)

### Phase 23: Auto-Recall Injection
**Goal**: Every agent session is automatically enriched with relevant memories from the store -- the bot applies institutional knowledge without anyone having to re-explain rules or context
**Depends on**: Phase 22
**Requirements**: RECALL-01, RECALL-02, RECALL-03, RECALL-04
**Success Criteria** (what must be TRUE):
  1. When Nicole asks the bot to do a task, the agent session prompt includes up to 5-8 relevant memories retrieved from the store based on the user's message -- visible in the bot's behavior (e.g., it follows a stored rule without being told)
  2. All memories categorized as "rule" are always included in recall regardless of query relevance -- rules are non-negotiable institutional knowledge
  3. When the bot uses a recalled memory to inform its response, it includes a brief citation (e.g., "Remembered: always dry_run first") so the team can see which memories influenced the output
  4. Fast-path commands (crawl, status, remember, recall, etc.) do not trigger auto-recall -- there is no latency regression on commands that bypass the agent pipeline
**Plans**: 1 plan

Plans:
- [ ] 23-01-PLAN.md — Auto-recall module and prompt injection wiring

### Phase 24: Post-Session Thread Scanning
**Goal**: The memory store grows organically from every bot conversation -- the team does not need to manually "remember" most knowledge because the bot extracts it automatically from threads
**Depends on**: Phase 23
**Requirements**: SCAN-01, SCAN-02, SCAN-03, SCAN-04, SCAN-05
**Success Criteria** (what must be TRUE):
  1. After an agent session completes, the bot automatically scans the thread and extracts memorable information (explicit directives, stated facts, corrections) via a lightweight Claude call -- without blocking the next queued task
  2. The bot only extracts from human messages in the thread -- it never stores content from its own replies (preventing echo loops where the bot memorizes its own output)
  3. Extraction is conservative: only explicit directives ("always do X", "never do Y", "the rule is Z") and stated facts are stored -- speculative statements, questions, and tentative language are skipped
  4. After each agent session, a one-line task summary (what was asked, what was done) is automatically stored as task history -- the team can later recall what the bot worked on
  5. Thread scanning runs as a fire-and-forget background task via asyncio -- completing in the background while the bot is already processing the next queued request
**Plans**: 1 plan

Plans:
- [ ] 24-01-PLAN.md — Thread scanner with extraction prompt, dedup, task history, and fire-and-forget wiring

## Progress

**Execution Order:**
Phases execute in order: 1 -> 2 -> 3 -> 4 -> v1.1 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17 -> 18 -> 19 -> 20 -> 21 -> 22 -> 23 -> 24

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. VM and Slack Bridge | v1.0 | 4/4 | Complete | 2026-03-19 |
| 2. Agent SDK Standalone | v1.0 | 3/3 | Complete | 2026-03-20 |
| 3. End-to-End Integration | v1.0 | 4/5 | In progress | - |
| 4. Operational Hardening | v1.0 | 0/1 | In progress | - |
| v1.1 Capability Parity | v1.1 | 1/TBD | In progress | - |
| 5. VM Validation and MCP Wiring | v1.2 | 2/2 | Complete | 2026-03-23 |
| 6. Read-Only Status and Storage Tools | v1.2 | 2/2 | Complete | 2026-03-23 |
| 7. Mutation Tools | v1.2 | 2/2 | Complete | 2026-03-23 |
| 8. Response Timing | v1.3 | 1/1 | Complete | 2026-03-24 |
| 9. Git Activity Logging | v1.4 | 1/1 | Complete | 2026-03-24 |
| 10. Digest Changelog | v1.4 | 1/1 | Complete | 2026-03-24 |
| 11. Fast-Path Crawl and Status | v1.5 | 1/1 | Complete | 2026-03-24 |
| 12. Background Tasks and Batch Crawl | v1.5 | 1/1 | Complete | 2026-03-24 |
| 13. Error UX | v1.5 | 1/1 | Complete | 2026-03-24 |
| 14. Progress Heartbeat | v1.6 | 1/1 | Complete | 2026-03-24 |
| 15. Deploy Script | v1.7 | 1/1 | Complete | 2026-03-25 |
| 16. Live Verification | v1.7 | 1/1 | Complete | 2026-03-25 |
| 17. Deploy Foundation | 2/3 | Complete    | 2026-03-25 | - |
| 18. Rollback | 1/1 | Complete    | 2026-03-25 | - |
| 19. Log Access | 1/1 | Complete    | 2026-03-25 | - |
| 20. Health Dashboard | v1.8 | Complete    | 2026-03-26 | - |
| 21. Pipeline Status | 1/1 | Complete   | 2026-03-26 | - |
| 22. SQLite Foundation and Memory Commands | 2/2 | Complete    | 2026-03-25 | - |
| 23. Auto-Recall Injection | 1/1 | Complete    | 2026-03-25 | - |
| 24. Post-Session Thread Scanning | 1/1 | Complete    | 2026-03-25 | - |
