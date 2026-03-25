import re
import time
from typing import Optional


def markdown_to_mrkdwn(text: str) -> str:
    """Convert standard markdown to Slack mrkdwn format.

    Preserves content inside ```code blocks``` — only converts non-code segments.
    """
    # Split into code blocks and non-code segments
    parts = re.split(r"(```[\s\S]*?```)", text)
    for i, part in enumerate(parts):
        if part.startswith("```"):
            continue  # skip code blocks
        # Bold: **text** → *text*  (must come before header conversion)
        part = re.sub(r"\*\*(.+?)\*\*", r"*\1*", part)
        # Bold: __text__ → *text*
        part = re.sub(r"__(.+?)__", r"*\1*", part)
        # Headers: # Header → *Header*
        part = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", part, flags=re.MULTILINE)
        # Links: [text](url) → <url|text>
        part = re.sub(r"\[(.+?)\]\((.+?)\)", r"<\2|\1>", part)
        # Horizontal rules: ---, ***, ___
        part = re.sub(r"^[-*_]{3,}\s*$", "", part, flags=re.MULTILINE)
        parts[i] = part
    return "".join(parts)


def format_status(
    current: Optional[dict],
    recent: list[dict],
    uptime: str,
    queue_snapshot: dict = None,
) -> str:
    """Format the /status response. Information-dense, scannable."""
    lines = ["*SuperBot Status*"]
    if current:
        elapsed = int(time.time() - current["started_at"])
        lines.append(f"Running ({elapsed}s): {current['text'][:100]}")
    elif queue_snapshot and queue_snapshot.get("current_task"):
        qt = queue_snapshot["current_task"]
        lines.append(f"Running: {qt.prompt[:100]}")
    else:
        lines.append("Idle")
    if queue_snapshot:
        depth = queue_snapshot.get("queue_depth", 0)
        if depth > 0:
            lines.append(f"Queued: {depth} task(s) waiting")
    if recent:
        lines.append(f"Recent ({len(recent)}):")
        for t in recent:
            lines.append(f"  - {t['text'][:80]}")
    lines.append(f"Uptime: {uptime}")
    return "\n".join(lines)


def format_error(summary: str, detail: str = "") -> str:
    """Format an error message. Summary only + key detail -- no stack traces."""
    msg = f"Error: {summary}"
    if detail:
        msg += f"\n{detail[:300]}"
    return msg


def format_completion(what_done: str, duration_s: int, files_changed: list[str] = None) -> str:
    """Format a task completion summary."""
    lines = [f"Done ({duration_s}s): {what_done}"]
    if files_changed:
        lines.append("Files: " + ", ".join(files_changed[:10]))
    return "\n".join(lines)


def format_queue_full(queue_depth: int, current_task_text: str) -> str:
    """Return rejection message when queue is at capacity."""
    return (
        f"Queue full ({queue_depth} pending + 1 running). "
        f"Currently: {current_task_text[:80]}. "
        f"Try again when the queue clears."
    )


def format_queued_notify(position: int) -> str:
    """Return acknowledgment that task was queued."""
    return f"Queued at position {position}. I'll notify you when your task starts."


def split_long_message(text: str, max_chars: int = 3800) -> list[str]:
    """Split text for Slack's ~4000 char limit. Splits on newlines, never mid-word."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        # If a single line exceeds max_chars, hard-split it
        while len(line) > max_chars:
            if current:
                chunks.append("".join(current))
                current = []
                current_len = 0
            chunks.append(line[:max_chars])
            line = line[max_chars:]
        if current_len + len(line) > max_chars and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def format_pr_link(pr_url: str) -> str:
    """Return a formatted string for surfacing a PR URL in Slack."""
    return f"PR ready for review: {pr_url}"


def format_test_result(summary_line: str) -> str:
    """Return a formatted one-liner for test results."""
    return f"Tests: {summary_line}"
