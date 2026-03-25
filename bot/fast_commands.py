"""
Fast-path handlers for deploy queries that don't need the full agent pipeline.

Pattern-match incoming messages and run git queries directly, returning
formatted Slack responses in seconds instead of minutes.

Handlers return a string (matched) or None (fall through to agent pipeline).
The deploy guard returns None when the deploy should proceed -- it only
blocks when an agent task is running and "force" is not specified.
"""

import re

import structlog

from bot import queue_manager
from bot.deploy_state import (
    REPO_CONFIG,
    get_deploy_preview,
    get_repo_status,
    resolve_repo,
)

log = structlog.get_logger(__name__)


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
# Command registry
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, async_handler_function)
# Handler receives the cleaned message text, returns formatted string or None.
# ORDER MATTERS: status and preview BEFORE guard so they don't fall through.
FAST_COMMANDS = [
    (_DEPLOY_STATUS_RE, _handle_deploy_status),
    (_DEPLOY_PREVIEW_RE, _handle_deploy_preview),
    (_DEPLOY_GUARD_RE, _handle_deploy_guard),
]


async def try_fast_command(text: str, slack_context: dict | None = None) -> str | None:
    """Check if text matches a fast command pattern.

    Returns the formatted response string if matched, or None if no match
    (caller should fall through to the full agent pipeline).
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
                return None
    return None
