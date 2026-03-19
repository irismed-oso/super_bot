import time
from typing import Optional


def format_status(current: Optional[dict], recent: list[dict], uptime: str) -> str:
    """Format the /status response. Information-dense, scannable."""
    lines = ["*SuperBot Status*"]
    if current:
        elapsed = int(time.time() - current["started_at"])
        lines.append(f"Running ({elapsed}s): {current['text'][:100]}")
    else:
        lines.append("Idle")
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
