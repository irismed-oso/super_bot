"""
Slack thread progress updates for running agent tasks.

Provides milestone detection from the Claude SDK AssistantMessage stream
and posting helpers for started, completion, and error messages.

Progress milestones are shown by editing a single message in-place
rather than posting new messages, to reduce thread clutter.
"""

import re

import structlog
from claude_agent_sdk import AssistantMessage, ToolUseBlock

from bot.formatter import markdown_to_mrkdwn, split_long_message

log = structlog.get_logger(__name__)

_READ_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "LS"}
_WRITE_TOOLS = {"Edit", "Write", "MultiEdit"}
PR_URL_RE = re.compile(
    r"https://github\.com/[^\s>]+/pull/\d+"
    r"|https://gitlab\.com/[^\s>]+/merge_requests/\d+"
)


async def post_started(
    client, channel: str, thread_ts: str, task_text: str
) -> dict | None:
    """Post a brief 'started' message and return its ts for later editing."""
    truncated = task_text[:80] + "..." if len(task_text) > 80 else task_text
    msg = f"Working on it: {truncated}"
    try:
        resp = await client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=msg
        )
        return {"ts": resp["ts"], "channel": channel}
    except Exception:
        log.warning("progress.post_started_failed", channel=channel)
        return None


def make_on_message(client, channel: str, thread_ts: str, progress_msg: dict | None = None):
    """
    Return an async callback for passing as on_message= to run_agent_with_timeout().

    The callback inspects each AssistantMessage for tool use blocks and edits
    the progress message in-place. Identical consecutive milestones are suppressed.
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
        elif "gh pr" in bash_cmd or "glab mr" in bash_cmd or "mr create" in bash_cmd:
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
                if progress_msg:
                    await client.chat_update(
                        channel=progress_msg["channel"],
                        ts=progress_msg["ts"],
                        text=milestone,
                    )
                else:
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


def _format_elapsed(duration_s: int) -> str:
    """Convert seconds to 'Xm Ys' format. Always shows both minutes and seconds."""
    minutes = duration_s // 60
    seconds = duration_s % 60
    return f"{minutes}m {seconds}s"


async def post_result(
    client, channel: str, thread_ts: str, result: dict, is_code_task: bool,
    duration_s: int | None = None,
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

    # Surface PR/MR URL prominently if present
    pr_match = PR_URL_RE.search(result.get("result", "") or "")
    if pr_match:
        msg += f"\n\nPR: {pr_match.group(0)}"

    # Append elapsed time footer
    if duration_s is not None:
        elapsed = _format_elapsed(duration_s)
        if subtype in error_subtypes:
            msg += f"\n\n_Failed after {elapsed}_"
        else:
            msg += f"\n\n_Completed in {elapsed}_"

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
