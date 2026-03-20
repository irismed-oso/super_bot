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
- [ ] 03-01-PLAN.md — glab CLI install script (scripts/setup_glab.sh) + DEPLOY.md Phase 3 section + VM verification checkpoint
- [ ] 03-02-PLAN.md — Worktree lifecycle module (bot/worktree.py) + agent cwd param + QueuedTask cwd field
- [ ] 03-03-PLAN.md — Progress module (bot/progress.py) + formatter extensions (format_mr_link, format_test_result)
- [ ] 03-04-PLAN.md — Handler wiring: replace _run_agent_stub with _run_agent_real + on_message threading
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

## Progress

**Execution Order:**
Phases execute in order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. VM and Slack Bridge | 4/4 | Complete    | 2026-03-19 |
| 2. Agent SDK Standalone | 3/3 | Complete    | 2026-03-20 |
| 3. End-to-End Integration | 0/5 | Not started | - |
| 4. Operational Hardening | 0/TBD | Not started | - |
