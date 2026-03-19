import asyncio
import time
from typing import Optional

_start_time = time.time()
_lock = asyncio.Lock()
_current_task: Optional[dict] = None   # {"text": str, "user": str, "started_at": float, "ts": str}
_recent_tasks: list[dict] = []          # last 5 completed tasks
_MAX_RECENT = 5


async def set_current(task: dict) -> None:
    """Set the currently running task. task keys: text, user, ts, started_at."""
    global _current_task
    async with _lock:
        _current_task = {**task, "started_at": time.time()}


async def clear_current() -> Optional[dict]:
    """Mark current task as done, move to recent. Returns the completed task."""
    global _current_task
    async with _lock:
        if _current_task:
            done = dict(_current_task)
            _recent_tasks.insert(0, done)
            if len(_recent_tasks) > _MAX_RECENT:
                _recent_tasks.pop()
            _current_task = None
            return done
        return None


def get_current() -> Optional[dict]:
    """Non-async read of current task (safe for sync contexts like /status handler)."""
    return _current_task


def get_recent(n: int = 5) -> list[dict]:
    """Return up to n most recent completed tasks."""
    return _recent_tasks[:n]


def get_uptime() -> str:
    """Return human-readable uptime string."""
    elapsed = int(time.time() - _start_time)
    h, m = divmod(elapsed // 60, 60)
    s = elapsed % 60
    if h:
        return f"{h}h {m}m"
    elif m:
        return f"{m}m {s}s"
    return f"{s}s"
