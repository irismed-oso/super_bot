from cachetools import TTLCache
import threading

_cache = TTLCache(maxsize=1000, ttl=600)  # 10-minute TTL covers Slack retry window
_lock = threading.Lock()


def is_seen(event_id: str) -> bool:
    """Return True if this event_id has been processed recently."""
    with _lock:
        return event_id in _cache


def mark_seen(event_id: str) -> None:
    """Mark event_id as processed. Call AFTER is_seen returns False."""
    with _lock:
        _cache[event_id] = True
