# Stack Research

**Domain:** Slack bot bridging to autonomous code agent on GCP VM
**Researched:** 2026-03-18
**Confidence:** HIGH (core decisions verified against official docs and PyPI)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `claude-agent-sdk` (Python) | 0.1.49 | Claude Code agent engine | Official Anthropic SDK. Bundles the Claude CLI automatically — no separate `claude` binary install needed. Avoids the documented TTY-hang bug in raw `claude -p` subprocess invocations (issues #9026, #13598). Provides `query()` with `resume=session_id` for persistent conversation across Slack messages. Async-native. |
| `slack-bolt` (Python) | 1.27.0 | Slack event handling framework | Official Slack SDK. Handles OAuth, signature verification, event routing, and message posting. Socket Mode adapter included — no public URL needed for a VM. Async variant (`AsyncApp`) pairs cleanly with `claude-agent-sdk`'s async API. |
| Python | 3.12 | Runtime | `claude-agent-sdk` requires >=3.10. Python 3.12 is current stable (3.13 is newest but 3.12 is better tested in production as of March 2026). |
| systemd | (OS-provided) | Process management | The bot is a long-lived daemon. systemd's `Restart=always`, journald logging, and `ExecStartPre` dependency ordering are standard on any GCP Debian/Ubuntu VM. No extra install. Simpler than Supervisor or Docker for a single-process service. |
| GCP Secret Manager | 2.26.0 (`google-cloud-secret-manager`) | Secrets storage | Stores `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `ANTHROPIC_API_KEY`. On a GCP VM with the right service account, secret access requires zero credential management — the VM's metadata server handles auth. Avoids `.env` files on disk. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `aiohttp` | 3.x (latest) | Async HTTP + Socket Mode transport | Required when using `AsyncSocketModeHandler` with `slack-bolt`'s async app. The sync `SocketModeHandler` uses `websocket-client` (bundled with `slack-bolt`) but the async variant needs `aiohttp`. Use async throughout — `claude-agent-sdk` is async-only. |
| `python-dotenv` | 1.x | Local development secrets | Load `.env` files in dev, fall back to Secret Manager in production. Never needed in production; only in the dev workflow. |
| `structlog` | 24.x | Structured logging | Produces JSON logs that GCP Cloud Logging can ingest and query. More useful than plain `logging` when you need to correlate a Slack `ts` (thread timestamp) with a Claude session ID. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Python dependency and venv management | Faster than pip. Use `uv pip install` and `uv venv`. Keeps the VM environment reproducible. |
| systemd journal (`journalctl`) | Log tailing in production | `journalctl -u super-bot -f` streams logs. No additional log aggregator needed for a small team. |
| `gh` CLI | GitLab/GitHub PR and repo operations | Pre-installed on the VM; Claude's Bash tool can call it. Needed for the deploy-from-VM flow. |

---

## Installation

```bash
# Create virtualenv
uv venv /opt/super_bot/.venv
source /opt/super_bot/.venv/bin/activate

# Core
uv pip install claude-agent-sdk==0.1.49 slack-bolt==1.27.0 aiohttp

# Secrets
uv pip install google-cloud-secret-manager==2.26.0

# Logging
uv pip install structlog

# Dev only
uv pip install python-dotenv
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `claude-agent-sdk` | Raw `claude -p` subprocess | Never on a VM daemon. The SDK wraps the same underlying CLI but handles TTY allocation internally and provides a proper async Python API. Use raw subprocess only for one-off shell scripts in CI/CD where a PTY exists. |
| Socket Mode (`AsyncSocketModeHandler`) | HTTP Events API (public URL) | Use HTTP if you later want to publish this app to Slack Marketplace (Socket Mode is ineligible) or need more than 10 concurrent WebSocket connections. For an internal VM with no public DNS, Socket Mode eliminates the need for a reverse proxy, Cloud NAT rule, or load balancer. |
| systemd | Docker / Cloud Run | Use Docker/Cloud Run if you want container isolation or auto-scaling. For a single-process bot on one VM with no scaling requirements, systemd is strictly simpler — no image builds, no registry, no container runtime to maintain. |
| GCP Secret Manager | Environment variables in `.env` | Use `.env` only in local development. On GCP VMs the metadata server handles IAM auth to Secret Manager without any key files. |
| `AsyncApp` + `AsyncSocketModeHandler` | Sync `App` + `SocketModeHandler` | Use sync only if you must support Python <3.10 or need to prototype quickly. The sync handler blocks the thread per Claude invocation, meaning concurrent Slack messages would queue. The async variant handles multiple requests without spawning threads. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Raw `subprocess.Popen(["claude", "-p", ...])` | Documented TTY-hang bug (GitHub issue #9026, unresolved Jan 2026): the CLI opens `/dev/tty` and blocks in a daemon context. The `workaround` (wrapping in `script -q /dev/null`) is fragile and unsupported. | `claude-agent-sdk` `query()` — same engine, proper async API, no TTY dependency. |
| Polling Slack REST API | Requires exposing a URL or running a tight poll loop. High API quota consumption, adds latency. | Socket Mode WebSocket — Slack pushes events in real time. |
| Flask / FastAPI for the bot server | HTTP mode needs a public HTTPS endpoint, TLS termination, and either a load balancer or `ngrok`-equivalent for the VM. Adds infrastructure for zero benefit on an internal tool. | Socket Mode — no HTTP server needed at all. |
| `Supervisor` | Additional install and config format to learn. No advantage over systemd on GCP Debian/Ubuntu. | systemd — already present, better journald integration. |
| Storing secrets in CLAUDE.md or `.env` committed to git | Secrets in plaintext in the repo would give anyone with repo access full bot + API key access. | GCP Secret Manager with VM service account IAM binding. |

---

## Stack Patterns by Variant

**If you need multi-user concurrency (>2 simultaneous requests):**
- Replace the single `AsyncApp` coroutine with a task queue (e.g., `asyncio.Queue`) so requests are processed in order per channel thread, not dropped.
- Claude Agent SDK sessions are per-process; concurrent `query()` calls for different Slack threads are fine (each has its own `session_id`).

**If the team grows and wants approval gates later:**
- Add a `PreToolUse` hook from the SDK's hook system to intercept destructive Bash commands and post a Slack confirmation message before proceeding.
- This is additive — no architecture change needed.

**If GitLab CI/CD integration is needed on the VM:**
- Add `GITLAB_TOKEN` to Secret Manager. The bot can call `gh`/`glab` CLI via the `Bash` tool — no separate integration layer needed.

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `claude-agent-sdk==0.1.49` | Python >=3.10 | Bundles claude CLI 2.1.71 internally. Do not install `claude` CLI separately — SDK uses its own bundled binary. |
| `slack-bolt==1.27.0` | Python 3.7+ | `AsyncApp` + `AsyncSocketModeHandler` require `aiohttp`. The sync `SocketModeHandler` uses `websocket-client` (bundled). |
| `aiohttp` 3.x | Python 3.8+ | Use latest 3.x. No known breaking changes with `slack-bolt` async adapters. |
| `google-cloud-secret-manager==2.26.0` | Python 3.7+ | GCP VM must have `roles/secretmanager.secretAccessor` on its service account. |

---

## Architecture Note for the Roadmap

The central integration pattern is:

```
Slack (Socket Mode WS) → AsyncSocketModeHandler
  → @app.event("app_mention") handler
  → claude_agent_sdk.query(prompt, options=ClaudeAgentOptions(
        cwd="/opt/mic_transformer",
        resume=session_id,           # per Slack channel thread ts
        allowed_tools=["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
        permission_mode="acceptEdits"
    ))
  → stream assistant messages back to Slack thread via WebClient.chat_postMessage
```

Session IDs are stored in a simple in-memory dict keyed by Slack thread `ts`. For the current scale (4 users, 1 channel), no persistent session store is needed — the SDK saves sessions to disk automatically under `~/.claude/projects/`.

---

## Sources

- `claude-agent-sdk` PyPI — version 0.1.49, Python >=3.10 requirement: https://pypi.org/project/claude-agent-sdk/
- Agent SDK overview (official Anthropic docs): https://platform.claude.com/docs/en/agent-sdk/overview
- Agent SDK Python reference: https://platform.claude.com/docs/en/agent-sdk/python
- Claude Code headless/CLI reference: https://code.claude.com/docs/en/headless
- Claude Code CLI flags reference: https://code.claude.com/docs/en/cli-reference
- TTY hang bug (unresolved): https://github.com/anthropics/claude-code/issues/9026
- Spurious /dev/tty reader bug: https://github.com/anthropics/claude-code/issues/13598
- `slack-bolt` PyPI — version 1.27.0: https://pypi.org/project/slack-bolt/
- Slack Socket Mode vs HTTP comparison: https://docs.slack.dev/apis/events-api/comparing-http-socket-mode/
- Slack Bolt Python Socket Mode adapter docs: https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/
- `google-cloud-secret-manager` PyPI — version 2.26.0: https://pypi.org/project/google-cloud-secret-manager/

---
*Stack research for: Slack-integrated Claude Code agent on GCP VM*
*Researched: 2026-03-18*
