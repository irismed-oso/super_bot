"""
Fast-path handlers for common queries that don't need the full agent pipeline.

Pattern-match incoming messages and run scripts/queries directly, returning
formatted Slack responses in seconds instead of minutes.

Handlers return a string (matched) or None (fall through to agent pipeline).
The deploy guard returns None when the deploy should proceed -- it only
blocks when an agent task is running and "force" is not specified.
"""

import asyncio
import os
import re
from datetime import date

import structlog

from bot import memory_store, prefect_api, queue_manager, background_monitor, task_state
from bot.deploy_state import (
    REPO_CONFIG,
    get_deploy_preview,
    get_last_deploy,
    get_repo_status,
    resolve_repo,
)

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Action-request detection -- skip fast commands when user wants a code change
# ---------------------------------------------------------------------------

_ACTION_STEMS = [
    "improv", "fix", "chang", "updat", "modif", "implement",
    "creat", "refactor", "remov", "delet", "mak", "enhanc", "rewrit",
    "build", "writ", "edit", "patch", "redesign", "rework", "replac",
    "migrat", "upgrad", "extend", "integrat", "includ",
]

# "add" needs exact word match to avoid "address", "additional", etc.
_ACTION_RE = re.compile(
    r"\b(?:(" + "|".join(_ACTION_STEMS) + r")\w*|add(ing|ed|s)?)\b",
    re.IGNORECASE,
)


def is_action_request(text: str) -> bool:
    """Return True if the message requests a code/system change rather than a query."""
    return bool(_ACTION_RE.search(text))


MIC_TRANSFORMER_DIR = os.path.realpath(
    os.environ.get("MIC_TRANSFORMER_CWD", "/home/bot/mic_transformer")
)
MIC_TRANSFORMER_PYTHON = os.path.join(MIC_TRANSFORMER_DIR, ".venv", "bin", "python")

# Timeout for fast command subprocess execution (seconds)
FAST_CMD_TIMEOUT = 30


async def _run_script(script_path: str, args: list[str], cwd: str = None) -> str:
    """Run a Python script and return its stdout. Raises on failure."""
    cmd = [MIC_TRANSFORMER_PYTHON, script_path] + args
    effective_cwd = cwd or MIC_TRANSFORMER_DIR

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=effective_cwd,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=FAST_CMD_TIMEOUT
    )

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"Script failed (exit {proc.returncode}): {err[:500]}")

    return stdout.decode().strip()


# ---------------------------------------------------------------------------
# Memory commands (v1.9) -- placed before deploy commands to avoid collisions
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
# Location aliases -- canonical names for all 23 EyeMed locations
# ---------------------------------------------------------------------------

LOCATION_ALIASES = {
    # Single-word locations (lowercase key -> canonical name)
    "boomtown": "Boomtown",
    "brenham": "Brenham",
    "clasik": "Clasik",
    "coastal": "Coastal",
    "dme": "DME",
    "eclant": "ECLANT",
    "ecec": "ECEC",
    "elite": "Elite",
    "emec": "EMEC",
    "feg": "FEG",
    "insights": "Insights",
    "lonestar": "LONESTAR",
    "msoc": "MSOC",
    "oec": "OEC",
    "optique": "OPTIQUE",
    "peg": "PEG",
    "premier": "Premier",
    "pvec": "PVEC",
    "tsoh": "TSOH",
    "tsos": "TSOS",
    "wagner": "Wagner",
    "westlake": "Westlake",
    # Multi-word locations (both hyphenated and space-separated)
    "optical image": "Optical Image",
    "optical-image": "Optical Image",
}

# Sorted by length descending so "optical image" matches before "optical"
_alias_keys_sorted = sorted(LOCATION_ALIASES.keys(), key=len, reverse=True)

# Dynamic regex that matches any known location name in the text
_LOCATION_EXTRACT_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _alias_keys_sorted) + r")\b",
    re.IGNORECASE,
)

# Words that should NOT be treated as location names in fallback parsing
_NON_LOCATION_WORDS = {"eyemed", "vsp", "all", "every", "each"}


# ---------------------------------------------------------------------------
# Deploy status: "deploy status" or "deploy status superbot"
# ---------------------------------------------------------------------------

_DEPLOY_STATUS_RE = re.compile(
    r"deploy\s+(?:status|info)(?:\s+(\S+))?", re.IGNORECASE
)


async def _handle_deploy_status(text: str, **kwargs) -> str:
    """Return formatted deploy status for one or all repos."""
    match = _DEPLOY_STATUS_RE.search(text)
    repo_filter = match.group(1) if match and match.group(1) else None

    if repo_filter:
        resolved = resolve_repo(repo_filter)
        if resolved is None:
            return f"Unknown repo: `{repo_filter}`. Known repos: {', '.join(REPO_CONFIG.keys())}"
        repos = [resolved[0]]
    else:
        repos = list(REPO_CONFIG.keys())

    lines = []
    for repo_name in repos:
        try:
            status = await get_repo_status(repo_name)
        except Exception as exc:
            lines.append(f"*{repo_name}* -- error: {exc}")
            continue

        header = f"*{repo_name}* (`{status['branch']}` @ `{status['sha']}`)"
        if status["behind"] > 0:
            detail = f"  {status['behind']} commit{'s' if status['behind'] != 1 else ''} behind origin/main"
        else:
            detail = "  Up to date"
        if status["dirty"]:
            detail += " (uncommitted changes)"
        last = get_last_deploy(repo_name)
        if last:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(last["deployed_at"], tz=timezone.utc)
            detail += f"\n  Last deployed: {dt.strftime('%Y-%m-%d %H:%M UTC')} (`{last['sha']}`)"
        lines.append(f"{header}\n{detail}")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Deploy preview: "deploy preview superbot"
# ---------------------------------------------------------------------------

_DEPLOY_PREVIEW_RE = re.compile(
    r"deploy\s+preview\s+(\S+)", re.IGNORECASE
)


async def _handle_deploy_preview(text: str, **kwargs) -> str:
    """Return the list of commits that would be deployed."""
    match = _DEPLOY_PREVIEW_RE.search(text)
    if not match:
        return "Usage: `deploy preview <repo>`"

    repo_text = match.group(1)
    resolved = resolve_repo(repo_text)
    if resolved is None:
        return f"Unknown repo: `{repo_text}`. Known repos: {', '.join(REPO_CONFIG.keys())}"

    repo_name = resolved[0]
    preview = await get_deploy_preview(repo_name)
    return f"*{repo_name}* pending commits:\n```\n{preview}\n```"


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
# Batch EyeMed crawl (must be checked BEFORE single-location crawl)
# ---------------------------------------------------------------------------

_BATCH_CRAWL_RE = re.compile(
    # "crawl all ...", "crawl eyemed all ...", "crawl for eyemed, all ..."
    r"crawl\s+(?:(?:for\s+)?eyemed\s*,?\s*)?(?:all\b|everything\b)"
    # "crawl eyemed" alone (not followed by a location name)
    r"|crawl\s+(?:for\s+)?eyemed\b(?!\s+[a-zA-Z])",
    re.IGNORECASE,
)


# Extract date-like arguments: MM.DD.YY, MM/DD/YY, "last N days", "past N days"
_DATE_RE = re.compile(r"\b(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)\b")
_DAYS_BACK_RE = re.compile(r"(?:last|past)\s+(\d+)\s+days?", re.IGNORECASE)
_LOCATION_RE = re.compile(
    r"\b(?:for|at|location)\s+([A-Za-z][\w\s]*?)(?:\s*(?:today|yesterday|status|$))",
    re.IGNORECASE,
)


def _normalize_date(d: str) -> str:
    """Normalize a date string to MM.DD.YY format, appending current year if missing."""
    parts = re.split(r"[./]", d)
    if len(parts) == 2:
        yy = str(date.today().year % 100).zfill(2)
        return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}.{yy}"
    elif len(parts) == 3:
        year_part = parts[2]
        if len(year_part) == 4:
            year_part = year_part[-2:]
        return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}.{year_part}"
    return d


def _today_mmddyy() -> str:
    """Return today's date as MM.DD.YY."""
    t = date.today()
    return f"{t.month:02d}.{t.day:02d}.{t.year % 100:02d}"


async def _handle_batch_crawl(text: str, slack_context: dict | None = None, **kwargs) -> str:
    """Trigger EyeMed crawl deployments for all 23 locations in parallel."""
    date_match = _DATE_RE.search(text)
    if date_match:
        date_str = _normalize_date(date_match.group(1).replace("/", "."))
    else:
        date_str = _today_mmddyy()

    canonical_locations = sorted(set(LOCATION_ALIASES.values()))

    location_pairs = [
        (loc, f"eyemed-crawler-{loc.lower().replace(' ', '-')}-manual")
        for loc in canonical_locations
    ]

    parameters_template = {
        "headless": True,
        "skip_s3": False,
        "skip_gcs": False,
        "skip_gdrive": False,
        "days_back": 1,
        "date_from": date_str,
        "date_to": date_str,
    }

    successes, failures = await prefect_api.trigger_batch_crawl(
        location_pairs, parameters_template,
    )

    if slack_context and successes:
        from bot.background_monitor import start_batch_monitor
        start_batch_monitor(slack_context, successes, date_str)

    lines = [f"Triggered batch crawl for {date_str}: {len(successes)} locations queued."]
    for loc, _run_id, run_name in sorted(successes):
        lines.append(f"  - {loc}: `{run_name}`")

    if failures:
        lines.append(f"\nFailed to trigger ({len(failures)}):")
        for loc, err in sorted(failures):
            lines.append(f"  - {loc}: {err}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Single-location EyeMed crawl
# ---------------------------------------------------------------------------

_EYEMED_CRAWL_RE = re.compile(
    r"crawl\s+(?:eyemed\s+)?(\S+)(?:\s+(.+))?",
    re.IGNORECASE,
)


async def _handle_eyemed_crawl(text: str, **kwargs) -> str:
    """Trigger a Prefect EyeMed crawl deployment for a single location."""
    m = _EYEMED_CRAWL_RE.search(text)
    if not m:
        return "Could not parse crawl command."

    raw_location = m.group(1).strip()
    date_part = m.group(2).strip() if m.group(2) else None

    canonical = LOCATION_ALIASES.get(raw_location.lower())
    if not canonical:
        valid = ", ".join(sorted(set(LOCATION_ALIASES.values())))
        return f"Unknown location '{raw_location}'. Known locations: {valid}"

    date_str = None
    if date_part:
        date_match = _DATE_RE.search(date_part)
        if date_match:
            date_str = date_match.group(1).replace("/", ".")
    if not date_str:
        date_match = _DATE_RE.search(text)
        if date_match:
            date_str = date_match.group(1).replace("/", ".")

    if not date_str:
        return "Please specify a date, e.g., 'crawl eyemed DME 03.20.26'"

    date_str = _normalize_date(date_str)

    deployment_name = f"eyemed-crawler-{canonical.lower().replace(' ', '-')}-manual"

    dep_id = await prefect_api.find_deployment_id(deployment_name)
    if not dep_id:
        return (
            f"Deployment '{deployment_name}' not found in Prefect. "
            "Check that the deployment exists and is active."
        )

    parameters = {
        "location": canonical,
        "headless": True,
        "skip_s3": False,
        "skip_gcs": False,
        "skip_gdrive": False,
        "days_back": 1,
        "date_from": date_str,
        "date_to": date_str,
    }

    result = await prefect_api.create_flow_run(dep_id, parameters)
    flow_run_id = result.get("id", "unknown")
    flow_run_name = result.get("name", "unknown")

    return (
        f"Triggered EyeMed crawl for {canonical} ({date_str})\n"
        f"Deployment: `{deployment_name}`\n"
        f"Flow run: `{flow_run_name}` ({flow_run_id[:8]})"
    )


# ---------------------------------------------------------------------------
# EyeMed status
# ---------------------------------------------------------------------------

_EYEMED_STATUS_RE = re.compile(
    r"eyemed\s+(?:scan\s+)?status"
    r"|(?:prep\s+)?status.*eyemed"
    r"|status\s+on\s+\S+\s+eyemed"
    r"|eyemed.*(?:today|yesterday|status|report|audit)"
    r"|prep\s+status\s+(?:for\s+)?eyemed",
    re.IGNORECASE,
)


async def _handle_eyemed_status(text: str, **kwargs) -> str:
    """Run the eyemed_scan_status.py script with args parsed from the message."""
    script = os.path.join(MIC_TRANSFORMER_DIR, "scripts", "eyemed_scan_status.py")
    if not os.path.isfile(script):
        raise FileNotFoundError(
            f"eyemed_scan_status.py not found at {script}. "
            "Has it been deployed to the VM?"
        )

    args = []

    # Parse days back
    days_match = _DAYS_BACK_RE.search(text)
    if days_match:
        args.extend(["--days", days_match.group(1)])

    # Parse explicit dates
    dates = _DATE_RE.findall(text)
    if len(dates) >= 2:
        d1 = _normalize_date(dates[0].replace("/", "."))
        d2 = _normalize_date(dates[1].replace("/", "."))
        args.extend(["--from", d1, "--to", d2])
    elif len(dates) == 1:
        d = _normalize_date(dates[0].replace("/", "."))
        args.extend(["--from", d])
        if re.search(r"\bto\s+(?:today|now)\b", text, re.IGNORECASE):
            args.extend(["--to", _today_mmddyy()])
        else:
            args.extend(["--to", d])

    # Handle "today" / "to today" when no explicit dates at all
    if not dates and "today" in text.lower() and not days_match:
        today = _today_mmddyy()
        args.extend(["--from", today, "--to", today])

    # Parse location: try smart extraction first, then fall back to old regex
    loc_match = _LOCATION_EXTRACT_RE.search(text)
    if loc_match:
        canonical = LOCATION_ALIASES.get(loc_match.group(1).lower())
        if canonical:
            args.extend(["--location", canonical])
    else:
        loc_match_old = _LOCATION_RE.search(text)
        if loc_match_old:
            captured = loc_match_old.group(1).strip().lower()
            # Skip non-location words like "eyemed", "vsp", etc.
            if captured not in _NON_LOCATION_WORDS:
                args.extend(["--location", loc_match_old.group(1).strip()])

    # Check for "yesterday"
    if "yesterday" in text.lower() and not dates:
        args.extend(["--days", "1"])

    output = await _run_script(script, args)
    return output


# ---------------------------------------------------------------------------
# Bot status query (handles "are you broken?", "are you stuck?", etc.)
# ---------------------------------------------------------------------------

_BOT_STATUS_RE = re.compile(
    r"(?:are\s+you\s+(?:broken|stuck|still\s+(?:going|running|working|there))|"
    r"what\s+(?:are\s+you\s+doing|is\s+(?:your|the)\s+status)|"
    r"you\s+(?:ok|okay|alive|there)\??|"
    r"bot\s+status)",
    re.IGNORECASE,
)


async def _handle_bot_status(text: str, **kwargs) -> str:
    """Return actual task state without spawning a full agent session."""
    state = queue_manager.get_state()
    monitors = background_monitor.get_active_monitors()
    current = state["current"]
    depth = state["queue_depth"]

    lines = []

    if current is not None:
        task_label = (current.clean_text[:100] if current.clean_text else current.prompt[:100])
        lines.append(f":gear: *Running a task*\n`{task_label}`\nQueue: {depth} waiting")

    for m in monitors:
        lines.append(
            f":satellite_antenna: *Background crawl in progress*\n"
            f"Tracking {m['run_count']} locations for {m['date_str']} "
            f"({m['elapsed_s']}s elapsed)"
        )

    if not lines:
        uptime = task_state.get_uptime()
        lines.append(f":white_check_mark: *Idle* -- no tasks running, no background jobs.\nUptime: {uptime}")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, async_handler_function)
# Handler receives the cleaned message text, returns formatted string or None.
# ORDER MATTERS:
# - Deploy status/preview BEFORE deploy guard (so they don't fall through)
# - Batch crawl BEFORE single crawl (so "crawl all" matches first)
# - Crawl BEFORE eyemed status (so "crawl eyemed DME" doesn't match status regex)
# - Bot status last (specific phrases won't collide with other commands)
FAST_COMMANDS = [
    # Memory commands (v1.9) -- must be first to avoid regex collisions
    (_REMEMBER_RE, _handle_remember),
    (_RECALL_RE, _handle_recall),
    (_FORGET_RE, _handle_forget),
    (_LIST_MEMORIES_RE, _handle_list_memories),
    # Deploy commands
    (_DEPLOY_STATUS_RE, _handle_deploy_status),
    (_DEPLOY_PREVIEW_RE, _handle_deploy_preview),
    (_DEPLOY_GUARD_RE, _handle_deploy_guard),
    # Crawl commands
    (_BATCH_CRAWL_RE, _handle_batch_crawl),
    (_EYEMED_CRAWL_RE, _handle_eyemed_crawl),
    (_EYEMED_STATUS_RE, _handle_eyemed_status),
    # Bot status
    (_BOT_STATUS_RE, _handle_bot_status),
]


async def try_fast_command(text: str, slack_context: dict | None = None) -> str | None:
    """Check if text matches a fast command pattern.

    Returns the formatted response string if matched, or None if no match
    (caller should fall through to the full agent pipeline).

    ``slack_context``, when provided, is a dict with ``client``, ``channel``,
    and ``thread_ts`` keys so handlers can spawn background tasks that post
    progress updates (e.g. batch crawl monitor).
    """
    if is_action_request(text):
        log.info("fast_command.skipped_action_request", text=text[:80])
        return None

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
