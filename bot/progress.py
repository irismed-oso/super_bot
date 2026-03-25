"""
Slack thread progress updates for running agent tasks.

Provides milestone detection from the Claude SDK AssistantMessage stream
and posting helpers for started, completion, and error messages.

Milestones are deduplicated -- the same milestone is never posted twice
in a row. Only 4-6 updates per task (per CONTEXT.md locked decision).
"""

import re

import structlog
from claude_agent_sdk import AssistantMessage, ToolUseBlock

from bot.formatter import markdown_to_mrkdwn, split_long_message

log = structlog.get_logger(__name__)

_READ_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "LS"}
_WRITE_TOOLS = {"Edit", "Write", "MultiEdit"}
PR_URL_RE = re.compile(r"https://github\.com/[^\s>]+/pull/\d+")


async def post_started(
    client, channel: str, thread_ts: str, task_text: str
) -> None:
    """Post a brief 'started' message to the Slack thread."""
    truncated = task_text[:80] + "..." if len(task_text) > 80 else task_text
    msg = f"Working on it: {truncated}"
    try:
        await client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=msg
        )
    except Exception:
        log.warning("progress.post_started_failed", channel=channel)


def make_on_message(client, channel: str, thread_ts: str):
    """
    Return an async callback for passing as on_message= to run_agent_with_timeout().

    The callback inspects each AssistantMessage for tool use blocks and posts
    milestone updates to the Slack thread. Identical consecutive milestones
    are suppressed.
    """
    last_milestone = None

    async def on_message_cb(message: AssistantMessage):
        nonlocal last_milestone

        tools = [
            b.name for b in message.content if isinstance(b, ToolUseBlock)
        ]
        bash_cmd = " ".join(
            b.input.get("command", "")
            for b in message.content
            if isinstance(b, ToolUseBlock) and b.name == "Bash"
        )

        # Determine milestone in priority order
        milestone = None
        if any(t in _WRITE_TOOLS for t in tools):
            milestone = "Making changes..."
        elif "gh pr" in bash_cmd:
            milestone = "Creating PR..."
        elif "pytest" in bash_cmd:
            milestone = "Running tests..."
        elif "git commit" in bash_cmd or "git push" in bash_cmd:
            milestone = "Committing changes..."
        elif any(t in _READ_TOOLS for t in tools):
            milestone = "Reading files..."

        if milestone is not None and milestone != last_milestone:
            last_milestone = milestone
            try:
                await client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts, text=milestone
                )
            except Exception:
                log.warning(
                    "progress.milestone_post_failed",
                    milestone=milestone,
                    channel=channel,
                )

    return on_message_cb


async def post_result(
    client, channel: str, thread_ts: str, result: dict, is_code_task: bool
) -> None:
    """Post the final result message to the Slack thread."""
    subtype = result.get("subtype", "")
    error_subtypes = {"error_timeout", "error_cancelled", "error_internal"}

    if subtype in error_subtypes:
        msg = _format_error(
            subtype,
            result.get("result", "") or "",
            result.get("partial_texts", []),
        )
    else:
        msg = _format_completion(result.get("result", "") or "", is_code_task)

    # Surface PR URL prominently if present
    pr_match = PR_URL_RE.search(result.get("result", "") or "")
    if pr_match:
        msg += f"\n\nPR: {pr_match.group(0)}"

    msg = markdown_to_mrkdwn(msg)
    chunks = split_long_message(msg)
    for chunk in chunks:
        try:
            await client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=chunk
            )
        except Exception:
            log.warning("progress.post_result_failed", channel=channel)


def _format_error(
    subtype: str, result_text: str, partial_texts: list
) -> str:
    """Format an error message based on subtype."""
    if subtype == "error_timeout":
        partial = partial_texts[-1] if partial_texts else "(nothing)"
        return f"Task timed out. Here's what was completed:\n{partial}"
    elif subtype == "error_cancelled":
        return "Task was cancelled."
    else:
        detail = result_text[:500] if result_text else "unknown error"
        return f"Task failed: {detail}"


def _format_completion(result_text: str, is_code_task: bool) -> str:
    """Format a completion message."""
    if not result_text:
        return "Done."
    return result_text
