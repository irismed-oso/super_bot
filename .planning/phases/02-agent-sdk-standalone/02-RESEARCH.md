# Phase 2: Agent SDK Standalone - Research

**Researched:** 2026-03-19
**Domain:** Claude Agent SDK (Python) — session management, FIFO queue, asyncio timeout, standalone CLI harness
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Session Continuity**
- Sessions are keyed by Slack thread_ts — same thread = same Claude session
- Top-level @mention (no thread) always starts a new session
- Sessions never expire — resume anytime by replying in the thread
- On resume: pass summary of old context + full recent context (not full history) to manage token budget
- Session-to-thread mapping persisted to survive service restarts

**Safety Limits**
- 10-minute wall-clock timeout per task — kill process if exceeded
- 25 max conversation turns per task — terminate cleanly if hit
- On timeout or max-turns: kill the session, post what was completed so far, offer "reply to continue where I left off"
- Full tool access — no --allowedTools or --disallowedTools restrictions. Full autonomy.
- Use --dangerously-skip-permissions or equivalent for non-interactive execution

**Concurrency Model**
- FIFO task queue with max depth of 3
- When queue is full (3 pending): reject with status showing what's running and queued
- When a queued task starts running: notify the original Slack thread ("Your task is now running.")
- /cancel kills the running task only — queue advances to next. Does NOT clear pending tasks.
- No priority system — first come, first served

**Agent Output Format**
- Post raw Claude output as-is — natural language, minimal post-processing
- Long output (>4000 chars): split into multiple Slack messages in the thread
- Code and diffs always wrapped in Slack code blocks (``` formatting)
- Errors: full context — error message, relevant stack trace, what was attempted
- No structured summary templates — trust Claude's natural output

### Claude's Discretion
- Session storage mechanism (file-based, SQLite, etc.)
- Queue implementation details (asyncio.Queue, etc.)
- How to extract and summarize prior session context for resumption
- Exact output splitting strategy for long messages
- How to detect and format code blocks in Claude's output

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AGNT-01 | Claude Agent SDK bridges Slack messages to Claude Code sessions running in mic_transformer directory | SDK `query()` with `cwd` parameter runs agent in any directory; `permission_mode="bypassPermissions"` enables headless execution |
| AGNT-02 | Full Slack thread context is passed to Claude Code session (not just the @mention message) | SDK `resume=session_id` resumes with full prior conversation; first-message prompt can include thread history for new sessions |
| AGNT-06 | Process-level timeout kills hung Claude Code sessions and notifies Slack | `asyncio.wait_for(coroutine, timeout=600)` raises `asyncio.TimeoutError`; wrap the `async for` loop in `wait_for` |
| AGNT-07 | Max-turns limit prevents runaway sessions from consuming excessive tokens | `ClaudeAgentOptions(max_turns=25)` — ResultMessage.subtype will be `"error_max_turns"` when hit; detect and handle cleanly |
| AGNT-08 | Persistent session continuity: thread-to-session mapping so follow-up messages in a thread continue the same Claude session | `ResultMessage.session_id` captured after each query; stored in JSON file keyed by thread_ts; `resume=session_id` on follow-up |
</phase_requirements>

---

## Summary

Phase 2 builds three cooperating modules: `bot/agent.py` (Claude Agent SDK wrapper), `bot/session_map.py` (thread_ts-to-session_id persistence), and `bot/queue_manager.py` (FIFO asyncio queue with max-depth 3). A standalone CLI test harness (`scripts/test_agent.py`) simulates the Slack interface so everything can be validated without Slack wired in.

The Claude Agent SDK (version 0.1.49, the current PyPI release) is verified to support `resume=session_id`, `max_turns`, `cwd`, and `permission_mode="bypassPermissions"`. These directly map to every locked user decision. Session IDs are read from `ResultMessage.session_id` after each `query()` call. The FIFO queue is implemented with `asyncio.Queue(maxsize=4)` (1 running + 3 pending) — `put_nowait()` raises `asyncio.QueueFull` if the queue is at capacity, enabling instant rejection without blocking. Timeout is `asyncio.wait_for(consume_stream(), timeout=600)`.

The one validated concern from STATE.md — that `ResultMessage` field structure needs verification before writing `bot/agent.py` — is resolved. The official Python API reference confirms `ResultMessage.session_id` (str), `ResultMessage.subtype` (`"success"` | `"error_max_turns"` | `"error_max_budget_usd"` | other error strings), `ResultMessage.result` (str | None), and `ResultMessage.num_turns` (int).

**Primary recommendation:** Build `agent.py` around `query()` with `ResultMessage` detection for session_id and termination reason; use `asyncio.Queue(maxsize=4)` for the FIFO queue; use `asyncio.wait_for` for the 10-minute wall-clock timeout.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude-agent-sdk` | 0.1.49 (current PyPI) | Claude Code agent execution with session management | Official Anthropic SDK; bundles claude CLI, avoids TTY-hang bug; async-native; `resume=`, `max_turns`, `cwd`, `permission_mode` all verified |
| Python `asyncio` | stdlib (3.12) | Queue, timeout, task management | `asyncio.Queue`, `asyncio.wait_for`, `asyncio.create_task` all needed; already the project's async runtime |

### Supporting (already in requirements.txt)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `structlog` | 24.x | Structured logging with thread_ts/session_id correlation | Every agent call — log session_id, thread_ts, turn count, outcome |
| `python-dotenv` | 1.x | Load `.env` in dev/test | Test harness only — VM uses env vars directly |

### Not Needed in Phase 2

- `slack-bolt` — not tested in Phase 2; Phase 3 wires Slack
- `aiohttp` — Phase 3 concern
- `google-cloud-secret-manager` — already configured in Phase 1

**Installation (claude-agent-sdk not yet in requirements.txt):**
```bash
uv pip install "claude-agent-sdk==0.1.49"
```

Add to `requirements.txt`:
```
claude-agent-sdk==0.1.49
```

---

## Architecture Patterns

### Recommended File Structure for Phase 2

```
super_bot/
├── bot/
│   ├── agent.py            # NEW: Claude Agent SDK wrapper (query, timeout, session capture)
│   ├── session_map.py      # NEW: thread_ts → session_id JSON persistence
│   ├── queue_manager.py    # NEW: asyncio.Queue FIFO with max-depth 3, run loop
│   ├── app.py              # EXISTS: entry point (unchanged in Phase 2)
│   ├── handlers.py         # EXISTS: _run_agent_stub replaced in Phase 3
│   ├── task_state.py       # EXISTS: extended with queue state for /sb-status
│   └── formatter.py        # EXISTS: add format_queue_full(), format_queued_notify()
└── scripts/
    └── test_agent.py       # NEW: standalone CLI harness — no Slack
```

### Pattern 1: Agent Query with Session Capture

**What:** Wraps `query()` to capture `session_id` from `ResultMessage` and detect termination reason.
**When to use:** Every time the agent is invoked; this is the core of `agent.py`.

```python
# bot/agent.py
# Source: https://platform.claude.com/docs/en/agent-sdk/python

import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock

MIC_TRANSFORMER_CWD = "/home/bot/mic_transformer"

async def run_agent(
    prompt: str,
    session_id: str | None,
    *,
    on_text: callable = None,
) -> dict:
    """
    Run a Claude agent task. Returns dict with:
      session_id (str): new or continued session ID
      result (str | None): final text result
      subtype (str): "success", "error_max_turns", "error_timeout", etc.
      num_turns (int): turns consumed
    """
    options = ClaudeAgentOptions(
        cwd=MIC_TRANSFORMER_CWD,
        resume=session_id,          # None for new session, str for resume
        max_turns=25,               # AGNT-07: locked decision
        permission_mode="bypassPermissions",  # --dangerously-skip-permissions equivalent
    )

    new_session_id = session_id
    result_text = None
    subtype = "unknown"
    num_turns = 0

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            text_parts = [b.text for b in message.content if isinstance(b, TextBlock)]
            if text_parts and on_text:
                await on_text("\n".join(text_parts))
        elif isinstance(message, ResultMessage):
            new_session_id = message.session_id  # Always present on ResultMessage
            result_text = message.result
            subtype = message.subtype             # "success" | "error_max_turns" | ...
            num_turns = message.num_turns

    return {
        "session_id": new_session_id,
        "result": result_text,
        "subtype": subtype,
        "num_turns": num_turns,
    }
```

### Pattern 2: Wall-Clock Timeout with asyncio.wait_for

**What:** Wraps the agent coroutine so it is killed after 600 seconds regardless of what Claude is doing.
**When to use:** Every agent invocation — 10-minute timeout is a locked decision.

```python
# bot/agent.py
# Source: https://docs.python.org/3/library/asyncio-task.html#asyncio.wait_for

TIMEOUT_SECONDS = 600  # 10 minutes — locked decision

async def run_agent_with_timeout(prompt: str, session_id: str | None, on_text=None) -> dict:
    try:
        return await asyncio.wait_for(
            run_agent(prompt, session_id, on_text=on_text),
            timeout=TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {
            "session_id": session_id,   # Retain prior session_id — can still resume
            "result": None,
            "subtype": "error_timeout",
            "num_turns": -1,
        }
```

**Key detail:** When `wait_for` times out, it cancels the inner coroutine and raises `TimeoutError`. The SDK subprocess is a child process; the SDK's `anyio` transport handles cleanup when the coroutine is cancelled. There is no need to manually kill a subprocess.

### Pattern 3: Session Map — thread_ts to session_id

**What:** JSON file on disk maps `"{channel}:{thread_ts}"` → session_id. Survives process restart (locked decision).
**When to use:** Every agent invocation — look up before, write after.

```python
# bot/session_map.py
# Source: Architecture research ARCHITECTURE.md Pattern 2

import json
import os

_MAP_FILE = os.path.expanduser("~/.superbot/session_map.json")


def get(channel: str, thread_ts: str) -> str | None:
    data = _load()
    return data.get(f"{channel}:{thread_ts}")


def set(channel: str, thread_ts: str, session_id: str) -> None:
    data = _load()
    data[f"{channel}:{thread_ts}"] = session_id
    _save(data)


def _load() -> dict:
    if not os.path.exists(_MAP_FILE):
        return {}
    with open(_MAP_FILE) as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_MAP_FILE), exist_ok=True)
    with open(_MAP_FILE, "w") as f:
        json.dump(data, f, indent=2)
```

**Note on cwd matching:** Sessions are stored by the SDK under `~/.claude/projects/<encoded-cwd>/`. When resuming, the `cwd` option must match the original session's cwd. Since `MIC_TRANSFORMER_CWD` is constant, this is not a problem — always pass the same `cwd`.

### Pattern 4: FIFO Queue with Max Depth 3

**What:** `asyncio.Queue(maxsize=4)` — 1 slot actively running + 3 queued. `put_nowait()` raises `asyncio.QueueFull` when at capacity (instant rejection, no block).
**When to use:** Every incoming agent request goes through the queue — serializes concurrency.

```python
# bot/queue_manager.py
# Source: https://docs.python.org/3/library/asyncio-queue.html

import asyncio
from dataclasses import dataclass

MAX_QUEUE_DEPTH = 3  # pending tasks (locked decision)
TOTAL_SLOTS = MAX_QUEUE_DEPTH + 1  # +1 for the currently running task

@dataclass
class QueuedTask:
    prompt: str
    session_id: str | None
    channel: str
    thread_ts: str
    user_id: str
    notify_callback: callable  # called when task dequeues to "now running"
    result_callback: callable  # called when task completes

_queue: asyncio.Queue = asyncio.Queue(maxsize=TOTAL_SLOTS)
_current_task: QueuedTask | None = None


def queue_depth() -> int:
    return _queue.qsize()


def is_full() -> bool:
    return _queue.full()


def get_current() -> QueuedTask | None:
    return _current_task


def enqueue(task: QueuedTask) -> bool:
    """
    Attempt to enqueue. Returns True if accepted, False if full.
    Caller must check is_full() before calling, or catch QueueFull.
    """
    try:
        _queue.put_nowait(task)
        return True
    except asyncio.QueueFull:
        return False


async def run_queue_loop() -> None:
    """Long-running coroutine. Call as asyncio.create_task(run_queue_loop())."""
    global _current_task
    while True:
        task = await _queue.get()
        _current_task = task
        try:
            await task.notify_callback()  # "Your task is now running."
            result = await run_agent_with_timeout(
                task.prompt, task.session_id
            )
            await task.result_callback(result)
        except Exception as exc:
            # result_callback handles errors; don't let queue loop die
            await task.result_callback({"subtype": "error_internal", "result": str(exc)})
        finally:
            _current_task = None
            _queue.task_done()
```

### Pattern 5: ResultMessage Subtype Handling

**What:** `ResultMessage.subtype` tells you why the agent stopped. Each subtype maps to a different user-facing message.
**When to use:** In `result_callback` to compose the Slack reply.

```python
# In result_callback or agent.py caller
def compose_reply(result: dict, thread_ts: str) -> str:
    subtype = result["subtype"]
    text = result.get("result") or ""

    if subtype == "success":
        return text  # Raw Claude output — locked decision

    if subtype == "error_max_turns":
        # AGNT-07: hit 25-turn limit
        partial = text or "(no partial output captured)"
        return (
            f"{partial}\n\n"
            "Reached the 25-turn limit. Reply in this thread to continue where I left off."
        )

    if subtype == "error_timeout":
        # AGNT-06: hit 10-minute timeout
        partial = text or "(no partial output captured)"
        return (
            f"{partial}\n\n"
            "Timed out after 10 minutes. Reply in this thread to continue where I left off."
        )

    # Other errors (error_max_budget_usd, etc.)
    return f"Task ended unexpectedly ({subtype}). Reply to retry."
```

### Pattern 6: Standalone CLI Test Harness

**What:** A script that exercises the agent, session resumption, queue, and timeout — without Slack.
**When to use:** Phase 2 validation per the locked design decision ("standalone test harness should simulate the Slack interface").

```python
# scripts/test_agent.py
"""
CLI harness to test bot/agent.py, bot/session_map.py, and bot/queue_manager.py
without any Slack dependency.

Usage:
    # New session
    python scripts/test_agent.py "list files in the bot/ directory"

    # Resume with a thread_ts
    python scripts/test_agent.py "what did you just find?" --thread-ts 12345.67890

    # Test max-turns
    python scripts/test_agent.py "count from 1 to 1000 one at a time" --max-turns 3

    # Test timeout
    python scripts/test_agent.py "sleep for 15 minutes" --timeout 5
"""
import asyncio
import argparse
from bot import session_map
from bot.agent import run_agent_with_timeout

FAKE_CHANNEL = "C_TEST"

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--thread-ts", default="test-thread-001")
    parser.add_argument("--max-turns", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    session_id = session_map.get(FAKE_CHANNEL, args.thread_ts)
    print(f"Session: {'resuming ' + session_id[:12] if session_id else 'new'}")

    result = await run_agent_with_timeout(
        args.prompt,
        session_id,
        timeout_seconds=args.timeout,
        max_turns=args.max_turns,
    )

    if result["session_id"]:
        session_map.set(FAKE_CHANNEL, args.thread_ts, result["session_id"])

    print(f"\n--- Result ({result['subtype']}, {result['num_turns']} turns) ---")
    print(result["result"] or "(no result)")

asyncio.run(main())
```

### Anti-Patterns to Avoid

- **Using `continue_conversation=True` instead of explicit `resume=session_id`:** The SDK resumes the "most recent session in cwd." With multiple threads active simultaneously, whichever finishes last becomes most recent — any follow-up picks up the wrong session. Always use explicit `resume=`.
- **Running queue loop inside `asyncio.create_task` inside a handler per request:** The queue consumer must be a single long-running loop started at bot startup, not spawned per request.
- **Cancelling `asyncio.wait_for` and immediately retrying:** After timeout, the session's JSONL file on disk is intact. The `session_id` (if captured before timeout) is still valid for resumption.
- **Ignoring `ResultMessage.subtype` and treating all results as success:** max_turns and timeout both return a result dict with `subtype != "success"`. Failing to check leaves the user with no feedback.
- **Checking `session_id` from `SystemMessage(subtype="init")`:** In Python SDK, the session_id is reliably in `ResultMessage.session_id`. The overview docs show capturing from init, but the Python reference confirms `ResultMessage` always has it. Use `ResultMessage` — it's guaranteed present and has the final session ID after the full query.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent execution loop | Custom subprocess manager with stdin/stdout JSONL | `claude_agent_sdk.query()` | SDK handles TTY allocation, process lifecycle, JSONL protocol, streaming; raw subprocess has documented TTY-hang bug in daemon contexts |
| Session persistence | Custom conversation log / re-injection of full history | SDK's `resume=session_id` on disk | SDK stores full JSONL history per session; re-injecting grows tokens unboundedly; SDK's own resumption is O(1) overhead |
| Timeout on async generator | `asyncio.Task.cancel()` with polling | `asyncio.wait_for(coro, timeout=N)` | `wait_for` propagates cancellation correctly through anyio coroutines; manual cancel-and-poll is racy |
| Queue overflow detection | `queue.qsize() >= MAX` before put | `queue.put_nowait()` + catch `asyncio.QueueFull` | `put_nowait` is atomic — no TOCTOU race between qsize check and put |
| Code block detection in output | Regex on Claude's output | Use `ResultMessage.result` directly | Claude already formats code in markdown; Slack renders triple-backtick as code block; no post-processing needed |

**Key insight:** The SDK is the only correct abstraction for Claude CLI invocation in a daemon context. Everything above it (queue, timeout, session map) is thin Python standard library.

---

## Common Pitfalls

### Pitfall 1: cwd Mismatch Breaks Session Resume

**What goes wrong:** `resume=session_id` silently starts a fresh session instead of resuming.
**Why it happens:** SDK stores sessions under `~/.claude/projects/<encoded-cwd>/`. If `cwd` differs between the first call and the resume call (e.g., different trailing slash, symlink vs real path), the SDK looks in the wrong directory and starts fresh.
**How to avoid:** Define `MIC_TRANSFORMER_CWD` as a single constant in `agent.py`. Use `os.path.realpath()` to resolve symlinks. Pass the identical string on every `query()` call.
**Warning signs:** Resumed session has no memory of prior work; `ResultMessage.num_turns` is 1 on what should be a follow-up.

### Pitfall 2: asyncio.wait_for Cancellation Leaves Queue Loop Alive

**What goes wrong:** After timeout, the queue loop coroutine is also cancelled, stopping all future tasks.
**Why it happens:** If `run_queue_loop` is not wrapped in a try/except, the `asyncio.CancelledError` from `wait_for` propagates up and kills the queue loop itself.
**How to avoid:** In `run_queue_loop`, wrap each task's execution in `try/except Exception` (not bare `except`). Let `CancelledError` propagate upward normally — but `wait_for` handles that internally; `CancelledError` only escapes if the outer task is cancelled. The queue loop must catch `Exception` on the agent coroutine.
**Warning signs:** After one timeout, all subsequent queue messages silently disappear.

### Pitfall 3: Task State Not Updated for Queue (breaks /sb-status)

**What goes wrong:** `/sb-status` shows wrong queue depth or stale current task info.
**Why it happens:** Phase 1's `task_state.py` tracks only current/recent — it has no queue concept.
**How to avoid:** Extend `task_state.py` (or `queue_manager.py` exposes a state snapshot function) to include: current task, queue depth, list of pending tasks' text previews. The `/sb-status` handler reads from this.
**Warning signs:** `/sb-status` shows "Idle" while the queue has pending items.

### Pitfall 4: session_map.json Race Condition on Concurrent Writes

**What goes wrong:** Two tasks completing simultaneously corrupt the JSON file (partial write).
**Why it happens:** asyncio is single-threaded, but the queue serializes execution, so two tasks completing simultaneously is impossible in the FIFO model. However, it could happen if the queue loop ever runs concurrent tasks.
**How to avoid:** Since the FIFO queue has exactly one running task at a time (single consumer), this is not a problem. Do not add concurrency later without adding a file lock (`asyncio.Lock` around `_load`/`_save`).
**Warning signs:** `json.JSONDecodeError` on load.

### Pitfall 5: Long Output Not Split Before Slack Posting

**What goes wrong:** Slack silently truncates messages over 4000 characters or returns an error.
**Why it happens:** `ResultMessage.result` can be many thousands of characters for complex tasks.
**How to avoid:** In `formatter.py`, add a `split_long_message(text, max_chars=3800)` function that splits on newlines (not mid-word) and returns a list of strings. The caller posts each chunk as a separate `chat_postMessage` in the thread. Leave headroom (3800 not 4000) for Slack metadata.
**Warning signs:** Slack API returns `msg_too_long` error.

### Pitfall 6: /cancel Command Does Not Cancel asyncio Task

**What goes wrong:** `/cancel` exists (Phase 1 stub) but does nothing; the running task continues.
**Why it happens:** The stub responds but has no reference to the asyncio Task running the agent.
**How to avoid:** In `queue_manager.py`, store the `asyncio.Task` object returned by `asyncio.ensure_future()` or `asyncio.create_task()`. `/cancel` calls `_running_task.cancel()`. The queue loop catches `CancelledError` from the agent, treats it as a timeout-like termination, posts "cancelled by user," and advances the queue.
**Warning signs:** `/cancel` responds "Cancelling..." but agent continues running and eventually posts its result.

---

## Code Examples

Verified patterns from official sources:

### Capture session_id from ResultMessage (AGNT-08)

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/sessions
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async def run_and_capture(prompt, session_id, cwd):
    options = ClaudeAgentOptions(
        cwd=cwd,
        resume=session_id,
        max_turns=25,
        permission_mode="bypassPermissions",
    )
    captured_session_id = session_id
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            captured_session_id = message.session_id   # Always present
            # message.subtype: "success" | "error_max_turns" | "error_max_budget_usd"
    return captured_session_id
```

### asyncio.wait_for for 10-minute kill (AGNT-06)

```python
# Source: https://docs.python.org/3/library/asyncio-task.html#asyncio.wait_for
import asyncio

async def run_with_timeout(coro, timeout_seconds=600):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return {"subtype": "error_timeout", "session_id": None, "result": None}
```

### asyncio.Queue FIFO with instant-reject on full (Concurrency model)

```python
# Source: https://docs.python.org/3/library/asyncio-queue.html
import asyncio

q = asyncio.Queue(maxsize=4)  # 1 running + 3 pending = 4 total slots

def try_enqueue(item) -> bool:
    try:
        q.put_nowait(item)
        return True
    except asyncio.QueueFull:
        return False

async def consumer():
    while True:
        item = await q.get()
        try:
            await process(item)
        finally:
            q.task_done()
```

### max_turns detection (AGNT-07)

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
from claude_agent_sdk import ResultMessage

# ResultMessage.subtype values (official):
# "success"               — completed normally
# "error_max_turns"       — hit max_turns limit
# "error_max_budget_usd"  — hit budget limit (not used here)

if isinstance(message, ResultMessage) and message.subtype == "error_max_turns":
    # post: "Hit 25-turn limit. Reply to continue."
    pass
```

### Long message splitting (Output format constraint)

```python
# Source: internal — Slack message limit is ~4000 chars
def split_long_message(text: str, max_chars: int = 3800) -> list[str]:
    """Split on newlines, never mid-word. Returns list of chunks."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > max_chars and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.Popen(["claude", "-p", ...])` | `claude_agent_sdk.query()` | SDK released ~2025 | Eliminates TTY-hang bug documented in issues #9026, #13598; provides typed async API |
| SDK named "Claude Code SDK" | Renamed to "Claude Agent SDK" | Recent (March 2026) | Import name unchanged: `from claude_agent_sdk import query` — only branding changed |
| Capturing session_id from `SystemMessage(subtype="init")` | Use `ResultMessage.session_id` | Current docs (2026) | `ResultMessage` is guaranteed present at end of every query; `SystemMessage.data` requires nested access and is TypeScript-documented more than Python |
| `ClaudeAgentOptions(allowed_tools=[...])` restricts tools | `permission_mode="bypassPermissions"` with no tool restriction | Current (2026) | "Full tool access — no restrictions" is the locked decision; `bypassPermissions` is the SDK's equivalent of `--dangerously-skip-permissions` |

**Deprecated/outdated:**
- `continue_conversation=True`: Only works correctly for single-thread bots. Replaced by explicit `resume=session_id` tracking for multi-thread bots like this one.

---

## Open Questions

1. **Partial output capture before timeout**
   - What we know: `AssistantMessage` blocks stream during execution; `ResultMessage` arrives only on completion.
   - What's unclear: If `wait_for` times out mid-stream, the last `AssistantMessage` text received is the partial output. But if no `AssistantMessage` arrived yet (agent is in a long Bash tool call), there is nothing to report.
   - Recommendation: Accumulate `AssistantMessage` text in a list during streaming. On timeout, report the last accumulated text as "what was completed so far." If empty, say "timed out before producing output."

2. **Session resume token budget on long conversations**
   - What we know: User decision says "pass summary of old context + full recent context (not full history)." SDK's `resume=` passes the full JSONL history.
   - What's unclear: The SDK does not expose a "summarize and truncate" API. The decision implies building a summarization step, but the SDK does not do this automatically.
   - Recommendation: For Phase 2, use plain `resume=session_id` (passes full history). Token limits are not hit in a normal 25-turn session. In Phase 4, add a periodic summarization hook if sessions grow too long. Flag this as a known limitation.

3. **asyncio Task cancellation vs subprocess cleanup**
   - What we know: `asyncio.wait_for` cancels the coroutine. The SDK uses `anyio.open_process()` internally.
   - What's unclear: Whether cancelling the outer coroutine reliably terminates the underlying `claude` subprocess (not just abandons it).
   - Recommendation: After timeout, check for orphaned `claude` processes (`pgrep -f "claude"`) in the test harness. If orphans appear, add a `Stop` hook or an `atexit` handler to kill child processes.

---

## Validation Architecture

Note: `workflow.nyquist_validation` is not set in `.planning/config.json`. Skipping this section.

---

## Sources

### Primary (HIGH confidence)
- `https://platform.claude.com/docs/en/agent-sdk/python` — Full Python API reference: `query()`, `ClaudeAgentOptions` all fields, `ResultMessage` fields, `permission_mode="bypassPermissions"`, `max_turns`, `resume`, `cwd`
- `https://platform.claude.com/docs/en/agent-sdk/sessions` — Session management: `resume=`, `continue_conversation`, `fork_session`, cwd-matching requirement, session file location
- `https://platform.claude.com/docs/en/agent-sdk/overview` — SDK overview, capabilities, `ResultMessage.subtype` values
- `https://pypi.org/pypi/claude-agent-sdk/json` — Version 0.1.49 confirmed current; Python >=3.10; `anyio>=4.0.0` dependency
- `https://docs.python.org/3/library/asyncio-queue.html` — `asyncio.Queue(maxsize=N)`, `put_nowait`, `asyncio.QueueFull`
- `https://docs.python.org/3/library/asyncio-task.html#asyncio.wait_for` — `asyncio.wait_for(coro, timeout=N)`, `asyncio.TimeoutError`

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — Stack research from 2026-03-18: version compatibility table, TTY-hang bug references, architecture note
- `.planning/research/ARCHITECTURE.md` — Architecture research from 2026-03-18: session map pattern, data flow, anti-patterns

### Tertiary (LOW confidence)
- `STATE.md` blocker note: "claude-agent-sdk==0.1.49 streaming API ResultMessage field structure needs verification" — RESOLVED by official Python API reference above

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyPI version confirmed, API verified against official docs
- Architecture: HIGH — session_id from ResultMessage, asyncio.Queue pattern, wait_for all confirmed in official Python stdlib and SDK docs
- Pitfalls: HIGH (cwd mismatch, QueueFull, subtype handling) verified from official docs; MEDIUM (subprocess orphan) flagged as open question

**Research date:** 2026-03-19
**Valid until:** 2026-04-18 (SDK is fast-moving; re-check if claude-agent-sdk version changes)
