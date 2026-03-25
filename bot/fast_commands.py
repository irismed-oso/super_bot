"""
Fast-path handlers for memory commands and deploy/rollback guards.

Memory commands (remember, recall, forget, list memories) get instant
responses without queueing.  Deploy and rollback guards block when an
agent task is running unless "force" is specified; otherwise they return
None to let the message fall through to the agent pipeline.

All other commands (crawl, deploy status, bot status, etc.) flow through
to the agent pipeline for full handling.
"""

import re

import structlog

from bot import memory_store, queue_manager

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Memory commands (v1.9)
# ---------------------------------------------------------------------------

_REMEMBER_RE = re.compile(r"^\s*remember\b\s+(.+)", re.IGNORECASE | re.DOTALL)
_RECALL_RE = re.compile(
    r"^\s*(?:recall|what\s+do\s+you\s+know\s+about|what\s+do\s+you\s+remember\s+about)\b\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)
_FORGET_RE = re.compile(r"^\s*forget\b\s+(.+)", re.IGNORECASE | re.DOTALL)
_LIST_MEMORIES_RE = re.compile(
    r"^\s*list\s+memories(?:\s+(rules?|facts?|history|preferences?))?",
    re.IGNORECASE,
)

# Category normalization for list command filters
_CATEGORY_NORMALIZE = {
    "rules": "rule",
    "facts": "fact",
    "preferences": "preference",
}


async def _handle_remember(text: str, **kwargs) -> str:
    """Store a memory with auto-categorization."""
    match = _REMEMBER_RE.search(text)
    if not match:
        return "Usage: `remember [text to remember]`"

    content = match.group(1).strip()
    category = memory_store.categorize(content)

    ctx = kwargs.get("slack_context", {})
    source_user = ctx.get("user_id", "unknown")
    source_channel = ctx.get("channel", "")

    try:
        row_id = await memory_store.store(content, category, source_user, source_channel)
        if row_id is None:
            return "Failed to store memory. The memory system may be unavailable."
        display = content[:100] + ("..." if len(content) > 100 else "")
        return f"Remembered as *{category}*: _{display}_"
    except Exception:
        return "Failed to store memory. The memory system may be unavailable."


async def _handle_recall(text: str, **kwargs) -> str:
    """Search memories using FTS5 ranked search."""
    match = _RECALL_RE.search(text)
    if not match:
        return "Usage: `recall [search query]`"

    query = match.group(1).strip()
    results = await memory_store.search(query, limit=10)

    if not results:
        return f"No memories found matching '{query}'."

    lines = [f"Found {len(results)} memories matching \"{query}\":"]
    for i, mem in enumerate(results, 1):
        created = mem.get("created_at", "unknown")
        user = mem.get("source_user", "unknown")
        cat = mem.get("category", "?")
        content = mem["content"]
        mid = mem["id"]
        lines.append(f"{i}. [{cat}] {content} -- stored by <@{user}> on {created} (id: {mid})")

    return "\n".join(lines)


async def _handle_forget(text: str, **kwargs) -> str:
    """Delete a memory by ID or search query."""
    match = _FORGET_RE.search(text)
    if not match:
        return "Usage: `forget [id or search query]`"

    query = match.group(1).strip()

    # Check if query is a numeric ID for direct delete
    if query.isdigit():
        mem = await memory_store.get_by_id(int(query))
        if mem and mem.get("active", 0):
            await memory_store.deactivate(int(query))
            display = mem["content"][:80] + ("..." if len(mem["content"]) > 80 else "")
            return f"Forgot memory #{query}: _{display}_"
        return f"No active memory found with id {query}."

    # Search for matching memories
    results = await memory_store.search(query, limit=5)

    if not results:
        return f"No memories found matching '{query}'."

    if len(results) == 1:
        mem = results[0]
        await memory_store.deactivate(mem["id"])
        display = mem["content"][:80] + ("..." if len(mem["content"]) > 80 else "")
        return f"Forgot: _{display}_"

    # Multiple matches -- ask user to be specific
    lines = ["Multiple matches found. Use `forget {id}` to remove a specific one:"]
    for i, mem in enumerate(results, 1):
        display = mem["content"][:80] + ("..." if len(mem["content"]) > 80 else "")
        lines.append(f"{i}. _{display}_ (id: {mem['id']})")

    return "\n".join(lines)


async def _handle_list_memories(text: str, **kwargs) -> str:
    """List all memories, optionally filtered by category."""
    match = _LIST_MEMORIES_RE.search(text)
    category_filter = None

    if match and match.group(1):
        raw = match.group(1).strip().lower()
        category_filter = _CATEGORY_NORMALIZE.get(raw, raw)

    memories = await memory_store.list_all(category=category_filter, limit=50)

    if not memories:
        if category_filter:
            return f"No memories in category '{category_filter}'. Use `remember [text]` to add one."
        return "No memories stored yet. Use `remember [text]` to add one."

    # Group by category
    grouped: dict[str, list[dict]] = {}
    for mem in memories:
        cat = mem.get("category", "uncategorized")
        grouped.setdefault(cat, []).append(mem)

    lines = []
    for cat in sorted(grouped.keys()):
        items = grouped[cat]
        lines.append(f"*{cat.title()}* ({len(items)})")
        for mem in items:
            lines.append(f"- {mem['content']} (id: {mem['id']})")
        lines.append("")  # blank line between categories

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Deploy guard: "deploy superbot" or "deploy force superbot"
# Blocks if an agent task is running (unless "force" is present).
# Returns None to fall through to agent pipeline when deploy should proceed.
# ---------------------------------------------------------------------------

_DEPLOY_GUARD_RE = re.compile(
    r"deploy\s+(?:force\s+)?(\S+)\s*$", re.IGNORECASE
)


async def _handle_deploy_guard(text: str, **kwargs) -> str | None:
    """Check whether to block a deploy command.

    Returns a warning string if blocked, or None to let the message
    fall through to the agent pipeline for actual deploy execution.
    """
    current_task = queue_manager.get_current_task()
    if current_task is not None and "force" not in text.lower():
        task_label = (
            current_task.clean_text[:80]
            if current_task.clean_text
            else current_task.prompt[:80]
        )
        return (
            f"An agent task is currently running: _{task_label}_\n"
            "Use `deploy force <repo>` to proceed anyway."
        )
    # Fall through to agent pipeline
    return None


# ---------------------------------------------------------------------------
# Rollback guard: "rollback superbot" or "rollback force superbot"
# Blocks if an agent task is running (unless "force" is present).
# Returns None to fall through to agent pipeline when rollback should proceed.
# ---------------------------------------------------------------------------

_ROLLBACK_GUARD_RE = re.compile(
    r"rollback\s+(?:force\s+)?(\S+)(?:\s+([a-f0-9]{4,40}))?\s*$",
    re.IGNORECASE,
)


async def _handle_rollback_guard(text: str, **kwargs) -> str | None:
    """Check whether to block a rollback command.

    Returns a warning string if blocked, or None to let the message
    fall through to the agent pipeline for actual rollback execution.
    """
    current_task = queue_manager.get_current_task()
    if current_task is not None and "force" not in text.lower():
        task_label = (
            current_task.clean_text[:80]
            if current_task.clean_text
            else current_task.prompt[:80]
        )
        return (
            f"An agent task is currently running: _{task_label}_\n"
            "Use `rollback force <repo>` to proceed anyway."
        )
    # Fall through to agent pipeline
    return None


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, async_handler_function)
# Handler receives the cleaned message text, returns formatted string or None.
FAST_COMMANDS = [
    # Memory commands (v1.9)
    (_REMEMBER_RE, _handle_remember),
    (_RECALL_RE, _handle_recall),
    (_FORGET_RE, _handle_forget),
    (_LIST_MEMORIES_RE, _handle_list_memories),
    # Deploy guard
    (_DEPLOY_GUARD_RE, _handle_deploy_guard),
    # Rollback guard
    (_ROLLBACK_GUARD_RE, _handle_rollback_guard),
]


async def try_fast_command(text: str, slack_context: dict | None = None) -> str | None:
    """Check if text matches a fast command pattern.

    Returns the formatted response string if matched, or None if no match
    (caller should fall through to the full agent pipeline).

    ``slack_context``, when provided, is a dict with ``client``, ``channel``,
    and ``thread_ts`` keys so handlers can spawn background tasks that post
    progress updates.
    """
    for pattern, handler in FAST_COMMANDS:
        if pattern.search(text):
            try:
                log.info("fast_command.matched", pattern=pattern.pattern, text=text[:80])
                result = await handler(text, slack_context=slack_context)
                if result is not None:
                    log.info("fast_command.success", pattern=pattern.pattern)
                return result
            except Exception as exc:
                log.error(
                    "fast_command.failed",
                    pattern=pattern.pattern,
                    error=str(exc),
                )
                # Fall through to agent on failure
                return None
    return None
