"""
Fast-path handlers for memory commands, health dashboard, credential updates,
and deploy/rollback guards.

Memory commands (remember, recall, forget, list memories) get instant
responses without queueing.  The health dashboard ("bot health", "bot status",
"are you broken?", etc.) shows a compact system snapshot.  Credential update
commands write payer portal credentials to GCP Secret Manager.  Deploy and
rollback guards block when an agent task is running unless "force" is
specified; otherwise they return None to let the message fall through to the
agent pipeline.

All other commands (crawl, deploy status, etc.) flow through to the agent
pipeline for full handling.
"""

import re
import resource
import shutil
import subprocess
import sys
from datetime import datetime

import structlog

from bot import background_monitor, credential_manager, memory_store, queue_manager, task_state

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
# Health dashboard (v1.4)
# ---------------------------------------------------------------------------

_BOT_HEALTH_RE = re.compile(
    r"^\s*(?:bot\s+(?:health|status)|are\s+you\s+(?:broken|still\s+going|ok)|health\s+check)\s*\??$",
    re.IGNORECASE,
)


async def _handle_bot_health(text: str, **kwargs) -> str:
    """Return a compact health dashboard with system metrics."""
    # Status
    state = queue_manager.get_state()
    current = state["current"]
    if current is not None:
        task_label = (
            current.clean_text[:60] if current.clean_text else current.prompt[:60]
        )
        status_line = f":large_orange_circle: *Status:* Running: _{task_label}_"
    else:
        status_line = ":large_green_circle: *Status:* Idle"

    # Uptime
    uptime = task_state.get_uptime()
    uptime_line = f":clock1: *Uptime:* {uptime}"

    # Queue depth
    q_depth = state["queue_depth"]
    queue_line = f":inbox_tray: *Queue:* {q_depth} task{'s' if q_depth != 1 else ''} waiting"

    # Git version
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        sha = "unknown"
    version_line = f":label: *Version:* `{sha}`"

    # Memory (RSS in MB)
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == "darwin":
            rss_mb = usage.ru_maxrss / (1024 * 1024)  # bytes -> MB
        else:
            rss_mb = usage.ru_maxrss / 1024  # KB -> MB
        memory_line = f":brain: *Memory:* {rss_mb:.0f} MB RSS"
    except Exception:
        memory_line = ":brain: *Memory:* unavailable"

    # Disk
    try:
        disk = shutil.disk_usage("/")
        used_gb = disk.used / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)
        disk_line = f":floppy_disk: *Disk:* {used_gb:.1f} / {total_gb:.1f} GB used"
    except Exception:
        disk_line = ":floppy_disk: *Disk:* unavailable"

    # Recent tasks
    recent = task_state.get_recent(5)
    tasks_line = f":white_check_mark: *Recent tasks:* {len(recent)} completed"

    # Active monitors
    monitors = background_monitor.get_active_monitors()
    if monitors:
        labels = ", ".join(m["date_str"] for m in monitors)
        monitors_line = f":satellite: *Active monitors:* {len(monitors)} ({labels})"
    else:
        monitors_line = ":satellite: *Active monitors:* 0"

    # Errors (24h) -- journalctl, only works on Linux with systemd
    try:
        err_output = subprocess.check_output(
            [
                "journalctl", "-u", "superbot",
                "--since", "24 hours ago",
                "-p", "err", "--no-pager", "-q",
            ],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
        err_count = len([line for line in err_output.strip().split("\n") if line.strip()])
        if err_count > 0:
            errors_line = f":rotating_light: *Errors (24h):* {err_count}"
        else:
            errors_line = ":warning: *Errors (24h):* 0"
    except Exception:
        errors_line = ":warning: *Errors (24h):* unavailable"

    # Last restart
    try:
        restart_dt = datetime.fromtimestamp(task_state._start_time)
        restart_str = restart_dt.strftime("%Y-%m-%d %H:%M:%S")
        restart_line = f":arrows_counterclockwise: *Last restart:* {restart_str}"
    except Exception:
        restart_line = ":arrows_counterclockwise: *Last restart:* unknown"

    lines = [
        "*Bot Health Dashboard*",
        "",
        status_line,
        uptime_line,
        queue_line,
        version_line,
        memory_line,
        disk_line,
        tasks_line,
        monitors_line,
        errors_line,
        restart_line,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Credential update commands
# ---------------------------------------------------------------------------

# Flexible pattern: "update creds <payer> <location> <username> <password>"
# Also matches: "update credentials", "set creds", "set credentials"
_UPDATE_CREDS_RE = re.compile(
    r"^\s*(?:update|set)\s+cred(?:ential)?s?\s+"
    r"(eyemed|vsp)\s+"
    r"(\S+)\s+"
    r"(\S+)\s+"
    r"(\S+)",
    re.IGNORECASE,
)


async def _handle_update_creds(text: str, **kwargs) -> str:
    """Update payer portal credentials in GCP Secret Manager."""
    match = _UPDATE_CREDS_RE.search(text)
    if not match:
        return (
            "Usage: `update creds <eyemed|vsp> <location> <username> <password>`\n"
            "Example: `update creds eyemed peg jsmith newpass123`"
        )

    payer = match.group(1).lower()
    location_raw = match.group(2)
    username = match.group(3)
    password = match.group(4)

    # Normalize location using mic_transformer's canonical list
    try:
        import sys
        sys.path.insert(0, "/home/bot/mic_transformer")
        from scripts.slack_bot.locations import normalize_location, get_all_locations
        location = normalize_location(location_raw)
        all_locations = get_all_locations()
    except ImportError:
        # Fallback: use raw input as-is (dev environment without mic_transformer)
        location = location_raw
        all_locations = None

    # Warn if location didn't resolve to a known canonical name
    if all_locations and location not in all_locations and location == location_raw:
        return (
            f"Unknown location `{location_raw}`. Known locations:\n"
            + ", ".join(f"`{loc}`" for loc in all_locations)
        )

    try:
        secret_id = credential_manager.update_credentials(payer, location, username, password)
        return (
            f"Updated *{payer.upper()}* credentials for *{location}*\n"
            f"Secret: `{secret_id}` | User: `{username}`"
        )
    except Exception as exc:
        log.error("credential_update.failed", payer=payer, location=location, error=str(exc))
        return f"Failed to update credentials: {exc}"


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
    # Health dashboard (v1.4)
    (_BOT_HEALTH_RE, _handle_bot_health),
    # Credential update
    (_UPDATE_CREDS_RE, _handle_update_creds),
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
