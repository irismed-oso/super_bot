"""
FIFO task queue manager for serializing agent invocations.

All Slack @mentions flow through enqueue() -> run_queue_loop(). Only one
agent call is active at a time. Pending tasks wait in an asyncio.Queue
(max 3 pending + 1 running = 4 total slots).

cancel_running() cancels the active asyncio.Task so /cancel can abort
a long-running agent call without killing the queue loop.
"""

import asyncio
from dataclasses import dataclass
from typing import Callable

import structlog

from bot.agent import run_agent_with_timeout

log = structlog.get_logger(__name__)

MAX_QUEUE_DEPTH = 3   # max pending tasks
TOTAL_SLOTS = 4       # maxsize=4: 1 running + 3 pending

# Module-level state -- initialized lazily inside run_queue_loop()
_queue: asyncio.Queue | None = None
_current_task: "QueuedTask | None" = None
_running_asyncio_task: asyncio.Task | None = None


@dataclass
class QueuedTask:
    """A task waiting in (or running from) the queue."""

    prompt: str
    session_id: str | None
    channel: str
    thread_ts: str
    user_id: str
    clean_text: str = ""         # original user message for error formatting
    cwd: str | None = None      # worktree path for code-change tasks
    on_message: object = None    # async callable(AssistantMessage) for milestone detection
    notify_callback: Callable = None   # async -- called when task starts
    result_callback: Callable = None   # async -- called with result dict when done


def enqueue(task: QueuedTask) -> bool:
    """Add a task to the queue. Returns True on success, False if full."""
    if _queue is None:
        raise RuntimeError(
            "Queue not initialized -- call run_queue_loop() first"
        )
    try:
        _queue.put_nowait(task)
        return True
    except asyncio.QueueFull:
        return False


def is_full() -> bool:
    """Return True if the queue cannot accept more tasks."""
    return _queue is not None and _queue.full()


def queue_depth() -> int:
    """Return number of tasks waiting in the queue (excludes running task)."""
    return _queue.qsize() if _queue else 0


def get_current_task() -> "QueuedTask | None":
    """Return the currently running task, or None."""
    return _current_task


def get_state() -> dict:
    """Observable snapshot for /sb-status."""
    return {
        "current": _current_task,
        "queue_depth": queue_depth(),
        "is_full": is_full(),
    }


def cancel_running() -> bool:
    """Cancel the active agent call. Returns True if cancellation was requested."""
    if _running_asyncio_task is None or _running_asyncio_task.done():
        return False
    _running_asyncio_task.cancel()
    return True


async def run_queue_loop() -> None:
    """
    Long-running coroutine that processes tasks serially.

    Start once at bot startup with asyncio.create_task(run_queue_loop()).
    The loop survives individual task failures -- only the outer task
    cancellation (bot shutdown) stops it.
    """
    global _queue, _current_task, _running_asyncio_task

    _queue = asyncio.Queue(maxsize=TOTAL_SLOTS)
    log.info("queue_loop.started", total_slots=TOTAL_SLOTS)

    while True:
        task = await _queue.get()
        _current_task = task
        log.info(
            "queue_loop.task_start",
            user=task.user_id,
            channel=task.channel,
            prompt_preview=task.prompt[:80],
        )
        try:
            await task.notify_callback()
            coro = run_agent_with_timeout(task.prompt, task.session_id, cwd=task.cwd, on_message=task.on_message)
            _running_asyncio_task = asyncio.ensure_future(coro)
            result = await _running_asyncio_task
            await task.result_callback(result)
        except asyncio.CancelledError:
            # /cancel triggered -- treat as user-initiated cancellation
            log.info("queue_loop.task_cancelled", user=task.user_id)
            result = {
                "session_id": task.session_id,
                "result": None,
                "subtype": "error_cancelled",
                "num_turns": -1,
                "partial_texts": [],
            }
            await task.result_callback(result)
            # Do NOT re-raise -- let queue loop continue to next task
        except Exception as exc:
            log.exception("queue_loop.unexpected_error", error=str(exc))
            await task.result_callback({
                "session_id": task.session_id,
                "result": str(exc),
                "subtype": "error_internal",
                "num_turns": -1,
                "partial_texts": [],
            })
        finally:
            _current_task = None
            _running_asyncio_task = None
            _queue.task_done()
