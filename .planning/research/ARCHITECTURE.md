# Architecture Research

**Domain:** Slack-integrated autonomous agent / ChatOps automation
**Researched:** 2026-03-18
**Confidence:** HIGH (primary sources: official Slack Bolt docs, Claude Agent SDK official docs, OpenCode Slack integration analysis)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         SLACK                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Team Channel  @superbot <task description>              │    │
│  └───────────────────────────┬──────────────────────────────┘    │
└──────────────────────────────│───────────────────────────────────┘
                               │ WebSocket (Socket Mode, outbound)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                         GCP VM                                   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Slack Bridge (Python, slack-bolt AsyncApp)              │    │
│  │  - Listens for app_mention events                        │    │
│  │  - ack() within 3 seconds (lazy listener pattern)        │    │
│  │  - Maps thread_ts → session_id                           │    │
│  │  - Posts progress updates and final result back          │    │
│  └─────────────────────┬───────────────────────────────────┘    │
│                         │ asyncio subprocess                     │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Claude Agent SDK (claude-agent-sdk Python)              │    │
│  │  - query() or ClaudeSDKClient for stateful sessions      │    │
│  │  - Session stored to ~/.claude/projects/<cwd>/*.jsonl    │    │
│  │  - Streams ResultMessage, AssistantMessage back          │    │
│  └─────────────────────┬───────────────────────────────────┘    │
│                         │ subprocess + JSONL stdin/stdout        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Claude Code CLI (claude binary)                         │    │
│  │  - Executes tools: Bash, Read, Write, Edit, Grep, Glob   │    │
│  │  - Works in /home/.../mic_transformer clone              │    │
│  │  - git operations, script execution, deploys             │    │
│  └─────────────────────┬───────────────────────────────────┘    │
│                         │                                        │
│  ┌──────────────────────▼──────────────────────────────────┐    │
│  │  mic_transformer repo clone                              │    │
│  │  Python venv, .env, git remote → GitLab                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Session Store (filesystem)                              │    │
│  │  ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl     │    │
│  │  thread_ts → session_id map (simple JSON file)           │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Anthropic API      │
                    │   (HTTPS outbound)   │
                    └─────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Slack Bridge | Receive events from Slack, dispatch tasks, post results back | `slack-bolt` AsyncApp with Socket Mode, Python asyncio |
| Event Router | Route `app_mention` events to the right handler, enforce access control | Bolt listener with allowed-user check |
| Session Map | Map Slack `thread_ts` to Claude Agent SDK session IDs for continuity | JSON file on disk (simple) or SQLite (robust) |
| Task Runner | Run Claude agent as an asyncio background task, stream output back | `asyncio.create_task()` wrapping `claude_agent_sdk.query()` |
| Claude Agent SDK | Launch the Claude CLI, manage the agent loop, stream results | `claude-agent-sdk` Python package |
| Claude Code CLI | Execute tools: bash, git, file ops against the repo | `claude` binary installed on VM |
| mic_transformer clone | The codebase the agent operates on | Git repo with venv and .env configured |
| Session Store | Persist conversation history between Slack messages | `~/.claude/projects/` JSONL files (automatic, SDK-managed) |

## Recommended Project Structure

```
super_bot/
├── bot/
│   ├── __init__.py
│   ├── app.py              # Slack Bolt AsyncApp entry point, Socket Mode
│   ├── handlers.py         # app_mention listener, lazy listener setup
│   ├── agent.py            # Claude Agent SDK wrapper, query() / ClaudeSDKClient
│   ├── session_map.py      # thread_ts → session_id persistence
│   ├── access_control.py   # allowed user list enforcement
│   └── formatter.py        # Convert agent output to Slack message blocks
├── config.py               # Env var loading (SLACK_BOT_TOKEN, ANTHROPIC_API_KEY, etc.)
├── requirements.txt
├── .env                    # Secrets (not committed)
├── systemd/
│   └── superbot.service    # Systemd unit for auto-restart on VM
└── scripts/
    └── setup_vm.sh         # VM provisioning script
```

### Structure Rationale

- **bot/app.py:** Single entry point keeps the process model clear — one long-running Socket Mode WebSocket connection.
- **bot/agent.py:** Isolates all Claude Agent SDK calls so the SDK can be swapped or upgraded without touching Slack logic.
- **bot/session_map.py:** Explicit persistence of thread→session mapping is required because the SDK's `continue_conversation=True` only resumes the most recent session in a directory, which breaks when two threads are active simultaneously.
- **systemd/:** The bot must be always-on; systemd with `Restart=always` is the standard pattern for GCP VM persistent services.

## Architectural Patterns

### Pattern 1: Lazy Listener (Ack-then-Process)

**What:** Slack requires all events to be acknowledged within 3 seconds. Claude agent tasks take seconds to minutes. The lazy listener pattern splits the response into (a) immediate ack and (b) background processing.

**When to use:** Always — any Claude agent invocation will exceed 3 seconds.

**Trade-offs:** Simple and Bolt-native. Thread-based by default (ThreadPoolExecutor). Async variant available with `AsyncApp`.

**Example:**
```python
# bot/handlers.py
@app.event("app_mention", lazy=[run_agent_task])
async def handle_mention_ack(ack, say):
    await ack()
    await say("On it... :thinking_face:")

async def run_agent_task(body, say, client):
    user_id = body["event"]["user"]
    thread_ts = body["event"].get("thread_ts") or body["event"]["ts"]
    channel = body["event"]["channel"]
    text = body["event"]["text"]

    session_id = session_map.get(channel, thread_ts)

    async for message in agent.run(text, session_id=session_id, cwd="/path/to/mic_transformer"):
        # stream intermediate updates or collect final result
        ...

    await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=result)
```

### Pattern 2: Thread-to-Session Mapping

**What:** Each Slack thread represents one logical conversation. Map `(channel, thread_ts)` → Claude session ID so follow-up messages in the same thread resume the same agent context.

**When to use:** Always — without this, every message starts a blank session.

**Trade-offs:** Simple dict persisted to disk is sufficient for a team of 5. SQLite adds crash safety.

**Example:**
```python
# bot/session_map.py
import json, os

MAP_FILE = os.path.expanduser("~/.superbot/session_map.json")

def get(channel: str, thread_ts: str) -> str | None:
    data = _load()
    return data.get(f"{channel}:{thread_ts}")

def set(channel: str, thread_ts: str, session_id: str):
    data = _load()
    data[f"{channel}:{thread_ts}"] = session_id
    _save(data)

def _load() -> dict:
    if not os.path.exists(MAP_FILE):
        return {}
    with open(MAP_FILE) as f:
        return json.load(f)

def _save(data: dict):
    os.makedirs(os.path.dirname(MAP_FILE), exist_ok=True)
    with open(MAP_FILE, "w") as f:
        json.dump(data, f)
```

### Pattern 3: Agent SDK Streaming with Incremental Slack Updates

**What:** Claude agent tasks can take minutes. Stream intermediate AssistantMessage blocks back to Slack using message updates (not new posts) so the user sees progress.

**When to use:** For tasks expected to run more than ~10 seconds.

**Trade-offs:** Adds complexity to the formatter. Slack rate-limits `chat.update` calls (1/second per channel is safe). Worth it for UX.

**Example:**
```python
# bot/agent.py
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock

async def run(prompt: str, session_id: str | None, cwd: str):
    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
        resume=session_id,
        cwd=cwd,
    )
    async for message in query(prompt=prompt, options=options):
        yield message  # caller decides what to send to Slack
```

## Data Flow

### Request Flow (happy path)

```
User posts @superbot <task> in Slack thread
    ↓
Slack sends app_mention event via Socket Mode WebSocket
    ↓
Bolt receives event → lazy listener fires
    ↓
handle_mention_ack(): ack() + "On it..." reply (< 3 seconds)
    ↓ (background asyncio task)
run_agent_task(): look up session_id from thread_ts
    ↓
claude_agent_sdk.query(prompt, resume=session_id, cwd=repo_path)
    ↓
SDK spawns `claude` CLI subprocess, sends prompt via stdin JSONL
    ↓
Claude CLI calls Anthropic API, executes tools (Bash, Read, Edit, git...)
    ↓
Agent streams AssistantMessage, ResultMessage back via stdout JSONL
    ↓
SDK yields typed message objects to our async for loop
    ↓
Bot formatter converts to Slack message, posts/updates in thread
    ↓
On ResultMessage: save new session_id to session_map
```

### Session Continuity Flow

```
First message in thread:
  session_map.get(channel, thread_ts) → None
  query(prompt, resume=None)  → new session
  on ResultMessage → session_map.set(channel, thread_ts, session_id)

Follow-up message in same thread:
  session_map.get(channel, thread_ts) → "abc-123"
  query(prompt, resume="abc-123")  → resumes with full context
  agent already knows files it read, decisions made, etc.
```

### Key Data Flows

1. **Inbound (Slack → VM):** Socket Mode WebSocket, outbound from VM, no public URL required. Slack sends app_mention payload as JSON.
2. **Agent invocation (Bridge → Claude CLI):** Python subprocess via `anyio.open_process()`, JSONL over stdin/stdout. Bidirectional streaming.
3. **Outbound (VM → Slack):** `slack_sdk.WebClient.chat_postMessage()` / `chat_update()` over HTTPS. Uses `SLACK_BOT_TOKEN`.
4. **Session persistence (in-process → disk):** Claude Agent SDK writes `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` automatically. The bridge only needs to persist the `thread_ts → session_id` mapping.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-5 users, low volume | Single VM, single process, Socket Mode, asyncio — sufficient. No queue needed. |
| 5-20 users, concurrent requests | Add asyncio semaphore to cap concurrent Claude agent processes (each is CPU/memory-intensive). |
| 20+ users / high concurrency | Switch to Events API HTTP mode behind a load balancer + task queue (Celery/Redis) for agent jobs. Out of scope for v1. |

### Scaling Priorities

1. **First bottleneck:** Concurrent Claude agent processes — each runs the full Claude CLI subprocess which is memory-heavy. A semaphore limiting to 2-3 concurrent tasks is the right first mitigation.
2. **Second bottleneck:** Slack rate limits on `chat_postMessage` / `chat_update`. Use a simple token-bucket throttle or batch updates.

## Anti-Patterns

### Anti-Pattern 1: Synchronous Response (No Lazy Listener)

**What people do:** Call the Claude agent inside the main event handler synchronously.
**Why it's wrong:** Slack requires ack within 3 seconds. Claude tasks take 30+ seconds. Slack retries the event, triggering duplicate agent runs.
**Do this instead:** Always use the lazy listener pattern — ack immediately, run agent in background.

### Anti-Pattern 2: One Session Per User (Not Per Thread)

**What people do:** Map user ID → single Claude session, so all their messages share one context.
**Why it's wrong:** If Nicole asks two unrelated questions in different threads, the agent mixes contexts and produces confused answers.
**Do this instead:** Map `(channel, thread_ts)` → session. Each thread is a separate conversation. New threads start fresh; replies continue.

### Anti-Pattern 3: Using `continue_conversation=True` With Multiple Active Threads

**What people do:** Use the SDK's built-in `continue_conversation=True` (resume most recent session in the directory) instead of explicit session ID tracking.
**Why it's wrong:** If two threads are active simultaneously, whichever finishes last becomes "most recent," and the next resume in any thread picks up the wrong session.
**Do this instead:** Always capture `session_id` from `ResultMessage` and persist it in the session map. Use `resume=session_id` explicitly.

### Anti-Pattern 4: Polling for Agent Output (HTTP Polling)

**What people do:** Start agent in background, poll a status endpoint from Slack.
**Why it's wrong:** Adds latency, complexity, and an HTTP server the VM doesn't need.
**Do this instead:** Use asyncio streaming from the SDK. Post to Slack directly from the streaming loop as messages arrive.

### Anti-Pattern 5: HTTP Events API Without Public URL on a VM

**What people do:** Use Events API HTTP mode because Slack docs say it's "more production-ready."
**Why it's wrong:** The GCP VM is not publicly accessible. Exposing it requires firewall rules, TLS certs, and a static IP — unnecessary complexity for an internal bot.
**Do this instead:** Socket Mode. The VM initiates an outbound WebSocket to Slack's servers. No inbound rules needed. Slack's own docs explicitly endorse Socket Mode for "on-premise integrations with no ability to receive external HTTP requests."

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Slack | Socket Mode WebSocket (slack-bolt AsyncApp) | Bot Token + App Token required; app_mention event subscription |
| Anthropic API | HTTPS via Claude Agent SDK subprocess | `ANTHROPIC_API_KEY` env var on VM; SDK handles auth |
| GitLab | SSH git operations from Claude's Bash tool | SSH key on VM authorized against GitLab; Claude can push/PR |
| mic_transformer services | Claude's Bash tool executes scripts directly | Same network as VM; Prefect, Flask, psql all accessible |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Slack Bridge ↔ Agent SDK | Python async function call, `async for` streaming | No queue needed at this scale; direct call |
| Agent SDK ↔ Claude CLI | Subprocess stdin/stdout JSONL | SDK manages this; not directly visible to bridge code |
| Bridge ↔ Session Map | In-process function calls, JSON file on disk | Trivially simple; survives process restart |
| Claude CLI ↔ repo | Filesystem reads/writes, subprocess Bash | Claude runs in `cwd=/path/to/mic_transformer` |

## Build Order Implications

The component dependencies dictate this build sequence:

1. **VM setup + Claude CLI** — nothing else can be tested without this; it is the foundation.
2. **Agent SDK integration** — verify Claude can be invoked programmatically, sessions work, streaming works. Test in isolation (no Slack yet).
3. **Slack Bridge (Socket Mode, basic)** — connect to Slack, verify app_mention events arrive, post simple text back. No agent yet.
4. **Bridge + Agent wired together** — connect steps 2 and 3. The lazy listener fires the agent, result posts to thread.
5. **Session continuity** — add session map, verify follow-up messages resume correctly.
6. **Access control + polish** — allowed user filtering, error handling, output formatting.

Skipping step 2 (agent in isolation) before step 3 (Slack) is the most common mistake: debugging a broken agent loop through Slack is painful. Test them separately first.

## Sources

- [Claude Agent SDK Overview (official, March 2026)](https://platform.claude.com/docs/en/agent-sdk/overview) — HIGH confidence
- [Claude Agent SDK Sessions (official, March 2026)](https://platform.claude.com/docs/en/agent-sdk/sessions) — HIGH confidence
- [Slack Bolt for Python — Lazy Listeners (official)](https://docs.slack.dev/tools/bolt-python/reference/lazy_listener/index.html) — HIGH confidence
- [Slack: Comparing HTTP & Socket Mode (official)](https://docs.slack.dev/apis/events-api/comparing-http-socket-mode/) — HIGH confidence
- [OpenCode Slack Integration architecture (DeepWiki analysis)](https://deepwiki.com/anomalyco/opencode/6.3-slack-integration) — MEDIUM confidence
- [Claude Code System Architecture (DeepWiki)](https://deepwiki.com/anthropics/claude-code/1.1-system-architecture) — MEDIUM confidence
- [Slack bolt-python GitHub](https://github.com/slackapi/bolt-python) — HIGH confidence

---
*Architecture research for: Slack-integrated Claude Code autonomous agent (super_bot)*
*Researched: 2026-03-18*
