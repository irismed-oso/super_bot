# Phase 3: End-to-End Integration - Research

**Researched:** 2026-03-20
**Domain:** Slack-to-Claude-Code wiring, git worktrees, GitLab MR creation, pytest automation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Progress Updates**
- Key milestones only — started, reading files, making changes, running tests, done (4-6 updates max per task)
- Brief with context — "Reading bot/agent.py to understand the timeout logic" (explains why, not just what)
- All updates stay in the thread — channel stays clean
- Completion message includes diff summary only when code was changed; Q&A tasks just get the answer

**MR Creation Flow**
- Branch naming: `superbot/task-description` — clearly bot-authored
- Target branch: `develop`
- MR description includes: what was changed, link to triggering Slack thread, test results (if run), files changed
- Let Claude Code handle MR creation using whatever git/API approach it prefers — no prescriptive tool choice
- Claude already has GitLab PAT from Phase 1 .env

**Auto-Test Behavior**
- Claude decides when to run pytest — judges whether tests are relevant to what changed
- On test failure: Claude decides whether to post failure + stop, or attempt a fix
- Test results in Slack: one-line pass/fail summary ("Tests: 42 passed, 0 failed")

**Worktree Isolation**
- Code-change tasks get isolated worktrees; Q&A/read-only tasks run in the main repo
- Worktree naming: `worktree-{thread_ts}` — maps back to the Slack thread
- Cleanup: keep worktree until MR is merged (enables follow-up replies in thread)
- On task failure with uncommitted changes: git stash + report to Slack. Worktree stays for recovery.

### Claude's Discretion
- How to detect whether a task is "code change" vs "Q&A" for worktree decision
- Which agent SDK streaming events to use for progress updates
- How to construct Slack thread permalink for MR descriptions
- Exact pytest invocation command and output parsing
- Whether to attempt fixing failing tests or report and stop

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AGNT-03 | Progress updates posted to Slack thread as Claude Code works (started, key steps, done) | SDK streaming via `AssistantMessage` + `ToolUseBlock` enables tool-based milestones; `on_text` callback already in `run_agent()` |
| AGNT-04 | Completion summary posted to thread with what was done, files changed, and outcomes | `ResultMessage.result` contains final text; `formatter.format_completion()` already exists and needs extension |
| AGNT-05 | Error reporting: failures posted to Slack thread with error details and context | `run_agent_with_timeout()` returns `subtype` field covering error_timeout, error_cancelled, error_internal |
| GITC-01 | Bot can create branches, commit changes, and push to GitLab | Claude Code Bash tool runs git commands; bot user already has GitLab SSH key (INFRA-06) |
| GITC-02 | Bot can create merge requests on GitLab from Slack requests | `glab mr create -t "title" -d "desc" -b develop -y` — glab must be installed on VM |
| GITC-03 | Bot can read, search, and answer questions about the mic_transformer codebase | Handled by Claude Code's existing Bash/Read/Grep/Glob tools; no extra wiring needed |
| GITC-04 | Bot automatically runs pytest after code changes and reports results in Slack thread | Claude runs `pytest` via Bash tool; bot parses stdout with regex for summary line |
| GITC-05 | Each task runs in an isolated git worktree to prevent concurrent task conflicts | `git worktree add ../worktree-{thread_ts} -b superbot/task-desc` before agent start |
</phase_requirements>

---

## Summary

Phase 3 is an integration and wiring phase, not a capability-building phase. The two complete subsystems — the Slack bridge (Phase 1) and the Claude Agent SDK layer (Phase 2) — are connected. The stub `_run_agent_stub()` in `handlers.py` gets replaced with a real call path through `queue_manager.enqueue()`, and handlers gain progress callbacks that post milestone updates into the Slack thread.

The three new technical problems introduced in Phase 3 are: (1) SDK streaming event interpretation for progress milestones, (2) git worktree lifecycle management around each code-change task, and (3) GitLab MR creation via `glab` CLI. Each of these has a clear established pattern. The Claude Agent SDK's `AssistantMessage` yields `ToolUseBlock` entries that name exactly which tool is being called — `Read`, `Edit`, `Bash`, `Grep`, etc. — providing the hook for task-type detection and milestone posting without enabling verbose streaming.

Glab is not currently installed on this development machine (confirmed absent), but the syntax is straightforward and well-documented. Because the user decision lets Claude choose how to create the MR, the bot merely gives Claude the task in a prompt that mentions MR creation — Claude will invoke `glab` or the GitLab API directly via Bash as it sees fit. The bot only needs to detect the MR URL in Claude's output to surface it in Slack.

**Primary recommendation:** Replace `_run_agent_stub` with a `_run_agent_real` that calls `queue_manager.enqueue()` with proper notify/result callbacks, wraps code-change tasks in a worktree created before agent invocation and kept until MR merge, and posts 4-6 Slack thread updates using `AssistantMessage`-based milestone detection. The rest (MR creation, pytest, git operations) is delegated to Claude Code via the agent prompt.

---

## Standard Stack

### Core (existing, no new installs)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude-agent-sdk` | 0.1.49 | Agent streaming, `AssistantMessage`, `ToolUseBlock` | Already installed; `AssistantMessage.content` yields `ToolUseBlock` entries used for milestones |
| `slack-bolt` | 1.27.0 | Thread update posts via `client.chat_postMessage` | Already installed; `thread_ts` parameter routes all updates to the correct thread |
| `glab` CLI | 1.x (latest) | GitLab MR creation on VM | Official GitLab CLI; used by Claude Code's Bash tool; needs VM install |

### New dependency
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `glab` (system binary) | latest | Create MRs non-interactively | On VM only; Claude calls it via Bash |

**Installation on VM (not local):**
```bash
# glab install (Debian/Ubuntu on GCP VM)
curl -s https://packagecloud.io/install/repositories/gitlab/cli/script.deb.sh | sudo bash
sudo apt install glab -y
# Authenticate with existing GITLAB_TOKEN from .env
glab auth login --token "$GITLAB_TOKEN" --hostname gitlab.com
```

### No new Python packages needed
All wiring is within the existing `claude-agent-sdk`, `slack-bolt`, and `structlog` stack already in `requirements.txt`. Phase 3 is pure Python code changes.

---

## Architecture Patterns

### Recommended Project Structure (additions only)
```
bot/
├── handlers.py         # MODIFY: replace _run_agent_stub with real path
├── agent.py            # NO CHANGE: run_agent() / run_agent_with_timeout() unchanged
├── queue_manager.py    # NO CHANGE: QueuedTask, notify_callback, result_callback
├── worktree.py         # NEW: git worktree lifecycle (create, detect, stash, cleanup)
├── progress.py         # NEW: milestone posting logic (Slack thread updates)
├── session_map.py      # NO CHANGE
└── formatter.py        # EXTEND: add format_mr_link(), format_test_result()
```

### Pattern 1: Handler Replacement (stub → real)

**What:** Replace `_run_agent_stub` in `handlers.py` with a function that enqueues into `queue_manager` with the right notify and result callbacks.

**When to use:** The only place Slack event handling changes.

```python
# bot/handlers.py — _run_agent_real replaces _run_agent_stub
async def _run_agent_real(body, client, event):
    thread_ts = event.get("thread_ts") or event["ts"]
    channel = event["channel"]
    text = event.get("text", "")
    user_id = event.get("user", "")

    # Strip @mention from text before sending to agent
    import re
    clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

    session_id = session_map.get(channel, thread_ts)
    is_code_task = worktree.is_code_task(clean_text)

    worktree_path = None
    if is_code_task:
        worktree_path = await worktree.create(thread_ts, clean_text)

    async def notify_cb():
        await progress.post_started(client, channel, thread_ts, clean_text)

    async def result_cb(result: dict):
        # Save session
        if result.get("session_id"):
            session_map.set(channel, thread_ts, result["session_id"])
        # Post result to thread
        await progress.post_result(client, channel, thread_ts, result, is_code_task)

    task = QueuedTask(
        prompt=_build_prompt(clean_text, worktree_path, channel, thread_ts),
        session_id=session_id,
        channel=channel,
        thread_ts=thread_ts,
        user_id=user_id,
        notify_callback=notify_cb,
        result_callback=result_cb,
    )
    if not queue_manager.enqueue(task):
        depth = queue_manager.queue_depth()
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=formatter.format_queue_full(depth, ""),
        )
```

### Pattern 2: Progress Milestones via AssistantMessage ToolUseBlock

**What:** Pass an `on_text` callback to `run_agent_with_timeout()` that fires on each `AssistantMessage`. Inside the callback, inspect `ToolUseBlock` entries to determine what milestone to post.

**Why this approach (not StreamEvent):** Milestone updates are coarse-grained (4-6 per task), not character-by-character. `AssistantMessage` fires once per completed turn, yielding the full list of content blocks including all `ToolUseBlock` entries for that turn. This is enough to post "Reading files..." or "Making changes..." without the complexity of `include_partial_messages=True`.

**Tool name → milestone mapping:**
| Tool(s) seen in turn | Milestone text |
|----------------------|----------------|
| `Read`, `Grep`, `Glob` | "Reading files..." |
| `Edit`, `Write` | "Making changes..." |
| `Bash` (content has "pytest") | "Running tests..." |
| `Bash` (content has "git") | "Committing changes..." |
| `Bash` (content has "glab mr") | "Creating MR..." |

**Implementation in `bot/progress.py`:**
```python
# Source: Official Agent SDK Python reference
# https://platform.claude.com/docs/en/agent-sdk/python

from claude_agent_sdk import AssistantMessage, ToolUseBlock, TextBlock

_READ_TOOLS = {"Read", "Grep", "Glob", "WebSearch"}
_WRITE_TOOLS = {"Edit", "Write"}

async def make_on_text(client, channel: str, thread_ts: str):
    """Returns on_text callback for run_agent_with_timeout()."""
    last_milestone = None

    async def on_text_cb(message: AssistantMessage):
        nonlocal last_milestone
        # Detect milestone from tool use blocks
        tools = [b.name for b in message.content if isinstance(b, ToolUseBlock)]
        bash_inputs = [
            b.input.get("command", "") or b.input.get("restart", "")
            for b in message.content
            if isinstance(b, ToolUseBlock) and b.name == "Bash"
        ]
        bash_cmd = " ".join(bash_inputs).lower()

        if tools:
            if any(t in _WRITE_TOOLS for t in tools):
                milestone = "Making changes..."
            elif "glab mr" in bash_cmd or "mr create" in bash_cmd:
                milestone = "Creating MR..."
            elif "pytest" in bash_cmd:
                milestone = "Running tests..."
            elif "git commit" in bash_cmd or "git push" in bash_cmd:
                milestone = "Committing changes..."
            elif any(t in _READ_TOOLS for t in tools):
                milestone = "Reading files..."
            else:
                milestone = None

            if milestone and milestone != last_milestone:
                last_milestone = milestone
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=milestone,
                )

    return on_text_cb
```

**Note:** `run_agent()` in `bot/agent.py` currently accepts `on_text` as an `async callable(text: str)`. This needs updating to accept an `async callable(message: AssistantMessage)` — or the existing string callback can be kept as-is and a separate `on_message` callback added. The cleaner path is to change `on_text` to receive the full `AssistantMessage` object; this is a one-line change in `agent.py`.

### Pattern 3: Git Worktree Lifecycle

**What:** Before agent invocation for code-change tasks, create an isolated git worktree. After MR merge (or explicit cleanup), remove it.

**git worktree mechanics (from official git-scm.com docs):**
- `git worktree add <path> -b <branch>` — creates a linked worktree at `<path>` on a new branch
- `git worktree remove <path>` — removes a linked worktree (refuses if dirty by default; add `--force` to override)
- `git worktree list` — shows all worktrees
- Linked worktrees share the object store but have their own index and working tree
- A branch cannot be checked out in two worktrees simultaneously — the agent's branch is exclusive to its worktree

**Bot implementation in `bot/worktree.py`:**
```python
import asyncio
import os
import subprocess

MIC_TRANSFORMER_PATH = os.environ.get("MIC_TRANSFORMER_CWD", "/home/bot/mic_transformer")
WORKTREE_BASE = os.path.dirname(MIC_TRANSFORMER_PATH)  # parent dir

def worktree_path(thread_ts: str) -> str:
    return os.path.join(WORKTREE_BASE, f"worktree-{thread_ts}")

def branch_name(task_description: str) -> str:
    """Slugify description to superbot/task-description format."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", task_description.lower().strip())[:40].strip("-")
    return f"superbot/{slug}"

async def create(thread_ts: str, description: str) -> str:
    """Create a worktree for this thread. Returns path."""
    path = worktree_path(thread_ts)
    branch = branch_name(description)
    if os.path.exists(path):
        return path  # already exists (follow-up message in same thread)
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", path, "-b", branch,
        cwd=MIC_TRANSFORMER_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {stderr.decode()}")
    return path

async def stash(thread_ts: str) -> None:
    """Stash uncommitted changes in the worktree (on failure)."""
    path = worktree_path(thread_ts)
    if not os.path.exists(path):
        return
    await asyncio.create_subprocess_exec(
        "git", "stash", "--include-untracked",
        cwd=path,
    )

def is_code_task(prompt: str) -> bool:
    """
    Heuristic: does this prompt suggest file modification?
    Conservative: default to True for safety (worktrees are cheap).
    """
    readonly_keywords = [
        "what", "why", "how", "explain", "describe", "show me", "list",
        "find", "search", "read", "look at", "check", "tell me",
    ]
    lower = prompt.lower()
    return not any(lower.startswith(kw) or f" {kw} " in lower for kw in readonly_keywords)
```

### Pattern 4: Prompt Construction with Worktree Context

**What:** The prompt sent to the agent must tell Claude the working directory for this task (the worktree path, not the main repo).

**When to use:** Every code-change task.

```python
def _build_prompt(
    user_text: str,
    worktree_path: str | None,
    channel: str,
    thread_ts: str,
) -> str:
    """Construct the agent prompt with operational context injected."""
    slack_link = f"https://slack.com/archives/{channel}/p{thread_ts.replace('.', '')}"
    lines = [user_text]
    if worktree_path:
        lines += [
            "",
            f"Working directory for this task: {worktree_path}",
            f"This is an isolated git worktree. Commit your changes to this worktree's branch.",
            f"When creating an MR, target the 'develop' branch.",
            f"Include this Slack thread link in the MR description: {slack_link}",
        ]
    return "\n".join(lines)
```

**Note on Slack permalink:** The `chat.getPermalink` API method requires an API call. The workaround is constructing it from known values: `https://slack.com/archives/{channel_id}/p{ts_without_dot}` — this is the documented format for Slack deep links and works reliably for internal links. No additional API call needed.

### Pattern 5: Result Posting with MR Link Detection

**What:** The `result_callback` posts the completion message. If the result text contains an MR URL (GitLab MR URLs contain `/merge_requests/`), it gets surfaced prominently.

```python
# bot/progress.py
import re

MR_URL_RE = re.compile(r"https://gitlab\.com/[^\s]+/merge_requests/\d+")

async def post_result(client, channel: str, thread_ts: str, result: dict, is_code_task: bool):
    subtype = result.get("subtype", "unknown")
    result_text = result.get("result") or ""

    if subtype in ("error_timeout", "error_cancelled", "error_internal"):
        msg = _format_error(subtype, result_text, result.get("partial_texts", []))
    else:
        msg = _format_completion(result_text, is_code_task)

    # Surface MR URL prominently if found
    mr_match = MR_URL_RE.search(result_text)
    if mr_match:
        msg += f"\n\nMR: {mr_match.group(0)}"

    for chunk in formatter.split_long_message(msg):
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=chunk,
        )
```

### Pattern 6: Queue Manager Integration with Worktree CWD

**What:** `QueuedTask.prompt` already contains the worktree path injected into the prompt. However, `run_agent_with_timeout()` in `agent.py` uses the fixed `MIC_TRANSFORMER_CWD` constant. For worktree tasks, the agent must run with `cwd` set to the worktree path, not the main repo.

**How to handle:** `run_agent()` must accept an optional `cwd` parameter that overrides `MIC_TRANSFORMER_CWD`. The `QueuedTask` dataclass needs a `cwd` field. The queue loop passes it through.

This is a **small but critical interface change** to `bot/agent.py` and `bot/queue_manager.py`:

```python
# bot/agent.py — add cwd parameter to run_agent()
async def run_agent(
    prompt: str,
    session_id: str | None,
    *,
    cwd: str | None = None,       # NEW: overrides MIC_TRANSFORMER_CWD
    on_text=None,
    max_turns: int = MAX_TURNS,
) -> dict:
    effective_cwd = os.path.realpath(cwd) if cwd else MIC_TRANSFORMER_CWD
    options = ClaudeAgentOptions(
        cwd=effective_cwd,
        resume=session_id,
        max_turns=max_turns,
        permission_mode="bypassPermissions",
    )
    ...
```

```python
# bot/queue_manager.py — add cwd field to QueuedTask
@dataclass
class QueuedTask:
    ...
    cwd: str | None = None    # NEW: worktree path for code-change tasks
```

```python
# bot/queue_manager.py — queue loop passes cwd
coro = run_agent_with_timeout(task.prompt, task.session_id, cwd=task.cwd)
```

### Anti-Patterns to Avoid

- **Using `include_partial_messages=True` for progress updates:** Token-by-token streaming to Slack will hit rate limits. Milestone-level updates from `AssistantMessage` are sufficient and rate-safe.
- **Hardcoding MIC_TRANSFORMER_CWD in ClaudeAgentOptions:** The cwd must be the worktree path for code-change tasks, or session resume will silently break (sessions are stored per-cwd, so a resume with the wrong cwd starts a new session).
- **Running `glab mr create` from bot Python code directly:** Claude Code's Bash tool handles this. The bot only reads the resulting MR URL from `result.result` — no direct subprocess needed.
- **Removing the worktree on task completion:** Keep it until MR is merged so follow-up messages in the thread continue on the same branch in the same worktree.
- **Creating a new worktree if one already exists for this thread_ts:** The `create()` function must check for an existing path first — follow-up messages in a code-change thread reuse the existing worktree.
- **Posting progress for every `AssistantMessage`:** Many turns produce no tool calls (only text). Only post a milestone when a new tool category is seen and it's different from the last posted milestone.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GitLab MR creation | Custom Python `requests` calls to GitLab REST API | `glab mr create` via Claude's Bash tool | glab handles auth, branch push, interactive edge cases; Claude decides when to call it |
| pytest result parsing | Custom test runner or output parser | `subprocess.run(["pytest", ...])` → regex on stdout for summary line | pytest's `X passed, Y failed in Ns` summary line is stable across versions; one regex handles it |
| Slack thread permalink | `client.chat_getPermalink()` API call | String construction: `https://slack.com/archives/{channel}/p{ts_nodot}` | Saves an API call; the format is documented and stable for deep links |
| Worktree branch collision | Custom collision detection | Use unique `thread_ts` as worktree path suffix | `thread_ts` is already unique per Slack thread — guaranteed no collision |

**Key insight:** Phase 3 delegates all complex git operations to Claude Code. The bot scaffolds (create worktree, post progress, surface result), but the actual `git commit`, `git push`, `glab mr create`, and `pytest` invocations happen inside the agent's Bash tool. This is the design — don't try to intercept or reimplement those operations in bot code.

---

## Common Pitfalls

### Pitfall 1: CWD Mismatch Breaks Session Resume
**What goes wrong:** Agent runs in main repo (MIC_TRANSFORMER_CWD) for session creation, then a follow-up runs in the worktree. The resume silently starts a new session because `~/.claude/projects/` subdirectory is keyed by CWD.
**Why it happens:** `run_agent()` uses `MIC_TRANSFORMER_CWD` as a module constant, and session_map stores session_id keyed by thread_ts. If CWD changes between calls for the same thread, the SDK treats it as a new project.
**How to avoid:** For code-change tasks, always pass the same worktree path as `cwd` on both the initial call and any follow-up calls. Store `worktree_path` in session_map or derive it from `thread_ts`.
**Warning signs:** Claude doesn't remember the prior conversation in follow-up messages.

### Pitfall 2: `on_text` Receives String, Not AssistantMessage
**What goes wrong:** The existing `on_text` callback in `run_agent()` is called with `combined` (a string), not the full `AssistantMessage`. Milestone detection needs the `ToolUseBlock` list, which requires the full message object.
**Why it happens:** Phase 2 `run_agent()` was designed for simple text forwarding (test harness), not structured milestone detection.
**How to avoid:** Rename or add a callback parameter — e.g., `on_message(message: AssistantMessage)` — invoked with the full `AssistantMessage` object, alongside or replacing `on_text(text: str)`.
**Warning signs:** No milestone updates posted to Slack even though Claude is actively working.

### Pitfall 3: Worktree Already Exists on Follow-Up
**What goes wrong:** A second message in the same thread calls `git worktree add` for a path that already exists, crashing with `fatal: 'worktree-...' already exists`.
**Why it happens:** Follow-up messages reuse the same `thread_ts`, so `worktree_path(thread_ts)` is identical.
**How to avoid:** `worktree.create()` must check `os.path.exists(path)` first and return early if the worktree is already there.
**Warning signs:** Second message in a code-change thread fails with a git error.

### Pitfall 4: Queue Loop Doesn't Pass `cwd` to Agent
**What goes wrong:** `QueuedTask` carries the worktree `cwd` field, but `run_queue_loop()` calls `run_agent_with_timeout(task.prompt, task.session_id)` without `cwd`. The agent runs in the main repo instead of the worktree, and any `git commit` commits to the wrong branch.
**Why it happens:** `QueuedTask.cwd` was added as a new field but the queue loop wasn't updated.
**How to avoid:** When adding `cwd` to `QueuedTask`, simultaneously update the `run_agent_with_timeout()` call in `run_queue_loop()`.
**Warning signs:** Changes end up committed to whatever branch the main repo is on.

### Pitfall 5: Slack Rate Limiting on Rapid Progress Posts
**What goes wrong:** Bot posts a milestone update for every `AssistantMessage`, even consecutive turns with the same tool pattern. This can post 20+ updates for a long task, risking rate limiting.
**Why it happens:** No deduplication of milestone labels.
**How to avoid:** Track `last_milestone` per task and only post when the milestone label changes (as shown in Pattern 2).
**Warning signs:** Channel flooded with repeated "Reading files..." messages.

### Pitfall 6: glab Not Installed or Not Authenticated
**What goes wrong:** Claude tries to run `glab mr create` and gets `command not found` or `authentication required`.
**Why it happens:** `glab` is not in the standard Ubuntu packages and must be installed separately; it requires authentication against GitLab before use.
**How to avoid:** Install `glab` as part of Phase 3 VM setup task; authenticate using `GITLAB_TOKEN` from `.env` during setup.
**Warning signs:** MR creation step errors with shell command failure in agent output.

---

## Code Examples

Verified patterns from official sources:

### AssistantMessage ToolUseBlock inspection (for milestone detection)
```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
from claude_agent_sdk import AssistantMessage, ToolUseBlock, TextBlock

async for message in query(prompt=prompt, options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                print(f"Tool: {block.name}, input: {block.input}")
            elif isinstance(block, TextBlock):
                print(f"Text: {block.text}")
```

### Passing cwd to ClaudeAgentOptions
```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
options = ClaudeAgentOptions(
    cwd="/home/bot/worktree-1234567.890",  # worktree path
    resume=session_id,
    max_turns=25,
    permission_mode="bypassPermissions",
)
```

### git worktree add (asyncio subprocess)
```python
# Source: https://git-scm.com/docs/git-worktree
proc = await asyncio.create_subprocess_exec(
    "git", "worktree", "add", "/home/bot/worktree-1234567.890",
    "-b", "superbot/fix-timeout-logic",
    cwd="/home/bot/mic_transformer",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()
if proc.returncode != 0:
    raise RuntimeError(f"worktree add failed: {stderr.decode()}")
```

### glab mr create non-interactive
```bash
# Source: https://docs.gitlab.com/cli/mr/create/
# Run inside the worktree; -b targets develop; -y skips confirmation
glab mr create \
  -t "superbot: fix timeout logic in agent.py" \
  -d "What was changed: ...\nSlack thread: https://slack.com/archives/...\nTests: 42 passed" \
  -b develop \
  -y
```

### Slack thread permalink construction (no API call)
```python
# Source: https://api.slack.com/reference/deep-linking
def make_thread_permalink(channel: str, thread_ts: str) -> str:
    """Construct a deep-link permalink without an API call."""
    ts_nodot = thread_ts.replace(".", "")
    return f"https://slack.com/archives/{channel}/p{ts_nodot}"
```

### pytest one-line result parsing
```python
import re
import subprocess

def run_pytest(cwd: str) -> str:
    """Run pytest in cwd and return one-line summary."""
    result = subprocess.run(
        ["python", "-m", "pytest", "--tb=no", "-q"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # pytest summary line: "42 passed, 0 failed in 3.14s" or "5 failed in 1.23s"
    summary_re = re.compile(r"(\d+ passed)?[, ]*(\d+ failed)?.*in \d+[\.\d]*s")
    for line in reversed(result.stdout.splitlines()):
        if summary_re.search(line):
            return f"Tests: {line.strip()}"
    return "Tests: (no summary found)"
```
**Note:** Per the locked decision, Claude decides whether to run pytest. The bot does not invoke pytest directly — this pattern is what Claude Code will use inside its Bash tool. The bot only reads the test result from `result.result` and posts it.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Polling for agent output | `async for message in query()` streaming | Real-time milestones without extra latency |
| One global session per user | Per-thread session_id mapped by `(channel, thread_ts)` | Concurrent threads don't corrupt each other's context |
| Running all tasks in main repo | git worktree per task | Parallel tasks on separate branches, no checkout conflicts |
| `ResultMessage.result` only | `AssistantMessage.content[].ToolUseBlock` mid-stream | Enables milestone detection without token-level streaming |

---

## Open Questions

1. **Session resume across worktrees**
   - What we know: Claude Agent SDK sessions are stored under `~/.claude/projects/<encoded-cwd>/`. Changing `cwd` = new project directory = session not found.
   - What's unclear: Whether `session_id` from a session in the main repo can be resumed in the worktree (different cwd encoding) for a follow-up message.
   - Recommendation: For simplicity in Phase 3, treat all code-change tasks in their worktree and all Q&A tasks in the main repo as separate session namespaces. Store `worktree_path` alongside `session_id` in session_map. Don't attempt cross-cwd session resume.

2. **`on_text` vs `on_message` callback signature in agent.py**
   - What we know: The current `on_text` callback receives a `str` (combined text from a turn). Milestone detection needs `AssistantMessage` to inspect `ToolUseBlock`.
   - What's unclear: Whether to replace `on_text` with `on_message(AssistantMessage)` or add it as a second callback parameter.
   - Recommendation: Add `on_message: Callable[[AssistantMessage], Awaitable] | None = None` alongside `on_text`. Keep `on_text` for backward compatibility (test harness uses it). Invoke `on_message` in the `isinstance(message, AssistantMessage)` branch.

3. **glab install and auth on VM**
   - What we know: glab is not installed (confirmed on dev machine). It requires a separate install script and `glab auth login`. The GITLAB_TOKEN is in `.env`.
   - What's unclear: Whether `glab auth login --token` persists across bot process restarts (it stores to `~/.config/glab-cli/`), and whether the bot user's home dir has that file from Phase 1 setup.
   - Recommendation: Add a VM setup task (Wave 1 of Phase 3) that installs glab and authenticates. Verify with `glab mr list` before wiring the agent.

---

## Sources

### Primary (HIGH confidence)
- `https://platform.claude.com/docs/en/agent-sdk/python` — `AssistantMessage`, `ToolUseBlock`, `ResultMessage` field definitions; `on_text` callback; `ClaudeAgentOptions.cwd`
- `https://platform.claude.com/docs/en/agent-sdk/streaming-output` — `AssistantMessage` vs `StreamEvent` semantics; `include_partial_messages`; milestone approach
- `https://git-scm.com/docs/git-worktree` — `git worktree add`, `git worktree remove`, linked worktree behavior
- `https://docs.gitlab.com/cli/mr/create/` — `glab mr create -t -d -b -y` syntax
- Project source code: `bot/agent.py`, `bot/handlers.py`, `bot/queue_manager.py`, `bot/session_map.py`, `bot/formatter.py`, `config.py` (read directly)

### Secondary (MEDIUM confidence)
- `https://api.slack.com/reference/deep-linking` — thread permalink URL format `https://slack.com/archives/{channel}/p{ts_nodot}`
- `https://docs.slack.dev/reference/methods/chat.getPermalink/` — confirms `chat.getPermalink` requires `channel` + `message_ts`

### Tertiary (LOW confidence)
- None — all claims verified against official sources

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and in use; glab syntax verified against official docs
- Architecture: HIGH — wiring patterns derived directly from existing Phase 2 code; SDK types verified
- Pitfalls: HIGH — derived from code analysis of existing modules plus official docs on cwd/session behavior

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (claude-agent-sdk is fast-moving; re-verify if SDK version bumps)
