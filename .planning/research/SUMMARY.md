# Project Research Summary

**Project:** super_bot — Slack-integrated Claude Code autonomous agent
**Domain:** ChatOps / autonomous coding agent bridge on GCP VM
**Researched:** 2026-03-18
**Confidence:** HIGH

## Executive Summary

Super Bot is a ChatOps automation system that bridges Slack @mentions to a Claude Code agent running on a GCP VM, giving a small trusted team (Nicole, Han) the ability to trigger autonomous coding operations — git commits, PR creation, script execution, codebase Q&A — directly from Slack without approval gates or a web UI. The established pattern for this class of product is: Socket Mode WebSocket inbound (no public URL required), `claude-agent-sdk` for agent invocation (avoiding the documented TTY-hang bug in raw subprocess calls), lazy listener for Slack's 3-second ack requirement, and thread-to-session mapping for multi-turn conversation continuity. This pattern is validated by official Anthropic docs, official Slack Bolt docs, and multiple production implementations (Kilo, Mintlify, sleepless-agent).

The recommended stack is minimal and well-justified: `slack-bolt` AsyncApp with `AsyncSocketModeHandler` for event handling, `claude-agent-sdk==0.1.49` for agent invocation, `google-cloud-secret-manager` for credentials on GCP, and systemd for process management. All major technology choices have strong official documentation backing and the async stack is required (not optional) because `claude-agent-sdk` is async-only and the lazy listener pattern requires non-blocking event handling. The build order is dictated by architecture: VM and agent SDK must work in isolation before the Slack bridge is connected, because debugging a broken agent loop through Slack is significantly harder than testing the agent standalone.

The top risks are correctness risks that must be addressed in Phase 1, not retrofitted: the Slack 3-second timeout (requires lazy listener from day one), duplicate event processing (requires persistent event ID deduplication), credential exposure (requires a dedicated `bot` OS user with no SSH keys, secrets in GCP Secret Manager), and the bot infinite loop (requires `bot_id` filter on every event handler). Context window exhaustion and concurrent session corruption are Phase 2 concerns that shape the agent integration design — specifically, a serialization queue and a `--max-turns` cap must be built in before the Slack trigger is connected to avoid partial-state repo corruption.

## Key Findings

### Recommended Stack

The stack is intentionally narrow: two core libraries (`slack-bolt`, `claude-agent-sdk`) plus GCP-native secrets management and systemd for process control. The `claude-agent-sdk` replaces raw `subprocess.Popen(["claude", "-p", ...])` — the SDK bundles the Claude CLI internally and avoids a documented, unresolved TTY-hang bug (GitHub issues #9026, #13598) that affects daemon processes. Socket Mode eliminates the need for any public URL, TLS termination, or load balancer on the VM. Python 3.12 is the right runtime (3.13 is newer but less battle-tested; SDK requires >=3.10).

**Core technologies:**
- `claude-agent-sdk==0.1.49`: Agent engine — bundles Claude CLI, async-native, `resume=session_id` for persistent threads
- `slack-bolt==1.27.0` + `AsyncSocketModeHandler`: Event handling — no public URL, lazy listener built-in, official SDK
- `aiohttp` (latest 3.x): Required by the async Socket Mode adapter
- `google-cloud-secret-manager==2.26.0`: Secrets on GCP — zero credential management via VM metadata server
- `systemd` (OS-provided): Process management — `Restart=always`, journald logging, no extra install
- `structlog`: Structured JSON logging for Cloud Logging correlation

### Expected Features

The MVP is clearly defined and relatively small. The dependency graph shows that almost everything flows from getting a working `@mention → Claude Code session → Slack reply` loop, so that loop must be the sole focus of Phase 1.

**Must have (table stakes):**
- Named-user allowlist — any workspace member can trigger code execution without it
- @mention → Claude Code session — the core mechanic; nothing else matters without this
- Thread context passed to agent — bot is context-blind without it; every commercial implementation includes this
- Progress updates in thread (start + done minimum) — prevents duplicate retries from users
- Completion summary posted back — closes the loop; standard across all comparable products
- Error reporting to Slack — silent failures destroy trust faster than loud failures
- Git commit + push — table stakes for a coding agent
- PR creation — the most requested "concrete action" command

**Should have (differentiators):**
- Persistent CLAUDE.md project memory — eliminates repeated context from users; Devin Wiki equivalent
- Script execution for Prefect flows and operational tasks — core value for Nicole's workflow
- Task serialization / basic queue — prevents concurrent session corruption
- Automatic test running post-change — reduces review burden; trust-building

**Defer (v2+):**
- Isolated task workspaces (git worktrees per task) — high complexity; add when concurrency is actually a problem
- Task queue with /status slash commands — add when team needs backlog visibility
- Daily digest — passive awareness feature; low urgency
- Deployment from Slack — high blast radius; requires extensive trust first

**Anti-features to reject:**
- Approval gates for every destructive action — defeats the autonomy value; explicitly out of scope per PROJECT.md
- DM-based interaction — kills team awareness, a core design goal
- Real-time token-by-token streaming — Slack rate limits will get the bot banned

### Architecture Approach

The architecture is a four-layer stack: Slack Bridge (event routing, ack, result posting) → Claude Agent SDK wrapper (session management, streaming) → Claude Code CLI (tool execution in the repo) → mic_transformer repo clone (the target workspace). The bridge and SDK layers are separated deliberately so the SDK can be upgraded without touching Slack logic. The session map (`thread_ts → session_id`) is a required explicit component — the SDK's built-in `continue_conversation=True` is insufficient when multiple threads are active simultaneously and will route the wrong context to the wrong thread.

**Major components:**
1. Slack Bridge (`bot/app.py`, `bot/handlers.py`) — Socket Mode WebSocket, lazy listener, event routing, access control
2. Agent wrapper (`bot/agent.py`) — `claude-agent-sdk` `query()` calls, streaming, session lifecycle
3. Session map (`bot/session_map.py`) — `(channel, thread_ts)` → session ID, persisted to disk JSON (simple) or SQLite (robust)
4. Access control (`bot/access_control.py`) — allowlist by Slack user ID, checked before any Claude invocation
5. Formatter (`bot/formatter.py`) — converts agent AssistantMessage/ResultMessage to readable Slack blocks
6. systemd unit (`systemd/superbot.service`) — `Restart=always`, GCP Secret Manager injection at startup

### Critical Pitfalls

1. **Slack 3-second timeout causing duplicate agent runs** — use lazy listener pattern from day one; `ack()` immediately, run agent in background task; never retrofit this
2. **Duplicate event processing** — track `event_id` persistently (not in-memory); a process restart would clear in-memory deduplication and replay events as new tasks
3. **Running Claude Code without credential isolation** — create a dedicated `bot` OS user with no SSH keys, no cloud credentials; store all secrets in GCP Secret Manager; deny Claude access to `~/.ssh/` via `settings.json` denylist; CVE-2025-59536 demonstrates this attack vector is actively exploited
4. **Bot infinite loop (responding to own messages)** — check `event.bot_id` before processing every event; subscribe only to `app_mention`, not generic `message` events
5. **Concurrent sessions corrupting the shared repo** — serialize Claude invocations with an `asyncio.Lock` or queue before connecting the Slack trigger; two simultaneous sessions in the same working directory will corrupt each other

## Implications for Roadmap

Based on research, the component dependency graph dictates a clear phase structure. The architecture research explicitly defines the correct build order, the pitfalls research specifies which pitfalls belong in which phase, and the features research defines a clear MVP boundary.

### Phase 1: VM Provisioning and Slack Bridge Foundation

**Rationale:** Security and correctness concerns identified in pitfalls research must be addressed before any code runs on the VM. The Slack bridge lazy listener pattern is not retrofittable — it must be correct from the first deployed version. Architecture research confirms VM + agent SDK must be testable in isolation before connecting Slack.
**Delivers:** A GCP VM with a `bot` OS user, secrets in GCP Secret Manager, a running systemd service, a Slack app that responds to @mentions with an ack, access control enforcement, event deduplication, and bot message loop prevention.
**Addresses (features):** Named-user allowlist, @mention listener, error reporting to Slack
**Avoids (pitfalls):** Slack 3-second timeout, duplicate event processing, bot infinite loop, credential isolation/running as root, Slack signature verification

### Phase 2: Claude Agent SDK Integration (Standalone, No Slack)

**Rationale:** Architecture research explicitly recommends testing the agent invocation in isolation before wiring it to Slack. Debugging a broken agent loop through Slack is significantly harder. This phase also addresses the two agent-layer pitfalls (context exhaustion, concurrent session corruption) before they can cause damage.
**Delivers:** A standalone Python script that can invoke `claude-agent-sdk`, stream results, manage sessions (resume by `session_id`), serialize concurrent requests, and handle context exhaustion gracefully.
**Uses (stack):** `claude-agent-sdk==0.1.49`, `--max-turns` cap, `asyncio.Lock` for serialization
**Implements (architecture):** `bot/agent.py`, `bot/session_map.py`
**Avoids (pitfalls):** Context window exhaustion, process hang in headless mode, concurrent session corruption

### Phase 3: Bridge + Agent Integration (End-to-End MVP)

**Rationale:** With Phase 1 (Slack bridge) and Phase 2 (agent SDK) independently verified, wiring them together is a low-risk integration step. This phase delivers the full MVP and validates the core product hypothesis.
**Delivers:** @mention in Slack triggers a real Claude Code session on the VM, progress is posted to the thread, completion summary is posted, errors are reported. Git operations and PR creation work end-to-end.
**Addresses (features):** Full MVP feature set — @mention → session, thread context, progress updates, completion summary, error reporting, git commit + push, PR creation
**Implements (architecture):** `bot/handlers.py` wiring agent calls, `bot/formatter.py`, session continuity flow

### Phase 4: Operational Hardening and Differentiators

**Rationale:** Once the core loop is validated with real usage, add the differentiating features that elevate the product beyond a basic bridge: persistent project memory, script execution for Prefect flows, and basic task serialization improvements.
**Delivers:** CLAUDE.md project memory configured, Prefect flow execution working via bot commands, structured logging in Cloud Logging, task queue for visibility.
**Addresses (features):** Persistent CLAUDE.md memory, script execution (Prefect flows), task serialization, automatic test running post-change

### Phase Ordering Rationale

- Security and correctness (Phase 1) comes first because the lazy listener and event deduplication patterns cannot be retrofitted cleanly — they affect the entire event processing model
- Agent isolation (Phase 2) before integration (Phase 3) is dictated by debuggability — the architecture research explicitly warns against this sequencing mistake
- Differentiators (Phase 4) come after MVP validation because the feature research defines them as "add after validation," not at launch
- Deployment from Slack is deferred indefinitely — it is a v2+ feature that requires extensive trust-building first

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** GCP VM setup specifics (service account IAM bindings for Secret Manager, systemd unit file syntax for secret injection at startup) — operational details that vary by GCP project configuration
- **Phase 2:** `claude-agent-sdk` streaming API details — the SDK version (0.1.49) is recent; streaming behavior and `ResultMessage` structure should be verified against the live SDK before implementation

Phases with standard patterns (skip research-phase):
- **Phase 3:** The bridge + agent wiring follows directly from the established lazy listener pattern; no novel patterns involved
- **Phase 4:** CLAUDE.md configuration is well-documented; Prefect flow execution via Bash tool is straightforward given agent access to the VM

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core choices verified against official PyPI pages, official Anthropic SDK docs, official Slack Bolt docs; TTY bug verified against open GitHub issues |
| Features | MEDIUM | MVP features HIGH (official Claude Code in Slack docs + GitHub Copilot docs confirm pattern); differentiators MEDIUM (community implementations and competitor analysis) |
| Architecture | HIGH | Primary sources: official Slack Bolt lazy listener docs, official Claude Agent SDK sessions docs, OpenCode Slack integration analysis |
| Pitfalls | HIGH | Critical pitfalls verified across official security docs, official GitHub issues, and CVE disclosures; recovery strategies are standard incident response |

**Overall confidence:** HIGH

### Gaps to Address

- **GCP-specific IAM configuration:** Research describes the Secret Manager pattern at the concept level; the exact service account bindings, `roles/secretmanager.secretAccessor` assignment, and systemd `ExecStartPre` secret injection command need to be validated against the actual GCP project during Phase 1 implementation
- **`claude-agent-sdk` `ResultMessage` structure:** The streaming API yields `AssistantMessage`, `ResultMessage`, and `TextBlock` objects; the exact fields needed to extract `session_id` from `ResultMessage` should be verified against the live 0.1.49 package before `bot/agent.py` is written
- **GitLab-specific PR creation:** Architecture research references `gh`/`glab` CLI for GitLab MR creation; the exact `glab` command syntax and authentication flow for the VM's dedicated bot user needs verification during Phase 3
- **mic_transformer repo access on VM:** The VM must have the `mic_transformer` repo cloned with the correct Python venv and `.env` already configured; this prerequisite is assumed by the architecture but not covered in the research

## Sources

### Primary (HIGH confidence)
- Claude Agent SDK Overview (official Anthropic, March 2026): https://platform.claude.com/docs/en/agent-sdk/overview
- Claude Agent SDK Sessions (official Anthropic, March 2026): https://platform.claude.com/docs/en/agent-sdk/sessions
- Claude Code Headless/Programmatic Mode Docs: https://code.claude.com/docs/en/headless
- Claude Code Security Docs: https://code.claude.com/docs/en/security
- Slack Bolt for Python — Lazy Listeners (official): https://docs.slack.dev/tools/bolt-python/reference/lazy_listener/index.html
- Slack: Comparing HTTP and Socket Mode (official): https://docs.slack.dev/apis/events-api/comparing-http-socket-mode/
- Verifying Requests from Slack (official): https://api.slack.com/authentication/verifying-requests-from-slack
- Claude Code in Slack (official Anthropic docs): https://code.claude.com/docs/en/slack
- GitHub Copilot coding agent in Slack (official GitHub docs): https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-slack
- GitHub Issue #7497: Process Hangs Indefinitely in Headless Mode: https://github.com/anthropics/claude-code/issues/7497
- GitHub Issue #4722: Context Window Exhaustion: https://github.com/anthropics/claude-code/issues/4722
- TTY hang bug (unresolved): https://github.com/anthropics/claude-code/issues/9026

### Secondary (MEDIUM confidence)
- OpenCode Slack Integration architecture (DeepWiki analysis): https://deepwiki.com/anomalyco/opencode/6.3-slack-integration
- Kilo for Slack feature page: https://kilo.ai/features/slack
- Mintlify Slack coding agent design: https://www.mintlify.com/blog/we-built-our-coding-agent-for-slack
- Anthropic long-running agent harnesses: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Check Point Research: CVE-2025-59536 / CVE-2026-21852: https://research.checkpoint.com/2026/rce-and-api-token-exfiltration-through-claude-code-project-files-cve-2025-59536/
- Git Worktrees for Parallel AI Agents: https://www.nrmitchi.com/2025/10/using-git-worktrees-for-multi-feature-development-with-ai-agents/

### Tertiary (LOW confidence)
- Sleepless Agent (Claude Code + Slack task queue): https://github.com/context-machine-lab/sleepless-agent — community implementation, directionally useful for v2 task queue design
- SFEIR Institute: Claude Code Headless Mode Errors: https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/errors/ — statistics unverified but patterns corroborated by official docs

---
*Research completed: 2026-03-18*
*Ready for roadmap: yes*
