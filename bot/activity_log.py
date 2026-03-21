"""
Persistent activity log for daily digest.

Appends one JSON line per completed task to a date-stamped log file.
Log files live in /home/bot/activity_logs/ (configurable via env var).
Each line: {"ts": "...", "user": "...", "text": "...", "subtype": "...",
            "num_turns": N, "duration_s": N, "channel": "...", "thread_ts": "..."}
"""

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

LOG_DIR = Path(os.environ.get("ACTIVITY_LOG_DIR", "/home/bot/activity_logs"))


def _log_path(d: date) -> Path:
    """Return path for a given date's activity log."""
    return LOG_DIR / f"{d.isoformat()}.jsonl"


def append(entry: dict) -> None:
    """Append an activity entry to today's log file."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = _log_path(date.today())
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        log.error("activity_log.write_failed", error=str(exc))


def read_day(d: date) -> list[dict]:
    """Read all activity entries for a given date."""
    path = _log_path(d)
    if not path.exists():
        return []
    entries = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception as exc:
        log.error("activity_log.read_failed", date=d.isoformat(), error=str(exc))
    return entries


def read_yesterday() -> list[dict]:
    """Read activity entries from yesterday."""
    return read_day(date.today() - timedelta(days=1))


def cleanup_old(keep_days: int = 30) -> int:
    """Remove log files older than keep_days. Returns count of files removed."""
    if not LOG_DIR.exists():
        return 0
    cutoff = date.today() - timedelta(days=keep_days)
    removed = 0
    for path in LOG_DIR.glob("*.jsonl"):
        try:
            file_date = date.fromisoformat(path.stem)
            if file_date < cutoff:
                path.unlink()
                removed += 1
        except ValueError:
            continue
    return removed
