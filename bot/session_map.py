"""
Thread-to-session persistence for Claude Agent SDK sessions.

Maps "{channel}:{thread_ts}" -> session_id in a JSON file on disk.
Survives process restarts. Used by agent.py to resume sessions.

No locking needed: the FIFO queue (queue_manager.py) ensures only one
writer at a time. Do NOT add filelock or threading.Lock — the queue
serialization eliminates the race condition entirely.
"""

import json
import os
import tempfile

_MAP_FILE = os.path.expanduser("~/.superbot/session_map.json")


def _key(channel: str, thread_ts: str) -> str:
    return f"{channel}:{thread_ts}"


def _load() -> dict:
    """Load the session map from disk. Returns {} if file does not exist."""
    if not os.path.exists(_MAP_FILE):
        return {}
    with open(_MAP_FILE) as f:
        return json.load(f)


def _save(data: dict) -> None:
    """Atomically write the session map to disk via os.replace()."""
    dir_path = os.path.dirname(_MAP_FILE)
    os.makedirs(dir_path, exist_ok=True)
    # Write to a temp file in the same directory, then atomic rename
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, _MAP_FILE)
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get(channel: str, thread_ts: str) -> str | None:
    """Return session_id for a thread, or None if not found."""
    data = _load()
    entry = data.get(_key(channel, thread_ts))
    if isinstance(entry, dict):
        return entry.get("session_id")
    return entry  # backward compat: old entries are plain strings


def get_cwd(channel: str, thread_ts: str) -> str | None:
    """Return the CWD stored for a thread's session, or None."""
    data = _load()
    entry = data.get(_key(channel, thread_ts))
    if isinstance(entry, dict):
        return entry.get("cwd")
    return None


def set(channel: str, thread_ts: str, session_id: str, cwd: str | None = None) -> None:
    """Store a session_id (and optional CWD) for a thread. Atomic: load, update, save."""
    data = _load()
    data[_key(channel, thread_ts)] = {"session_id": session_id, "cwd": cwd}
    _save(data)


def delete(channel: str, thread_ts: str) -> None:
    """Remove a thread's session mapping. No-op if absent."""
    data = _load()
    key = _key(channel, thread_ts)
    if key in data:
        del data[key]
        _save(data)


def list_all() -> dict:
    """Return a copy of the full session map."""
    return _load()
