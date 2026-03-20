import time
from typing import Optional


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


def format_mr_link(mr_url: str) -> str:
    """Return a formatted string for surfacing an MR URL in Slack."""
    return f"MR ready for review: {mr_url}"


def format_test_result(summary_line: str) -> str:
    """Return a formatted one-liner for test results."""
    return f"Tests: {summary_line}"
