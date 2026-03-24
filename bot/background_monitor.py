"""
Background polling loop that tracks Prefect flow runs and posts Slack updates.

Runs as an ``asyncio.create_task()`` in the bot's event loop -- does NOT touch
the agent queue at all.  It's just async HTTP polls + Slack API calls.
"""

import asyncio
import time

import structlog

from bot import prefect_api

log = structlog.get_logger(__name__)

# How often to poll Prefect for updated flow-run states (seconds).
POLL_INTERVAL = 30

# Minimum interval between Slack progress messages (seconds).
UPDATE_INTERVAL = 150  # ~2.5 minutes

# Safety ceiling -- abort the monitor after this many seconds.
MAX_POLL_DURATION = 3600  # 1 hour

# Flow-run states considered terminal (no further polling needed).
_TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "CRASHED"})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_batch_monitor(
    slack_context: dict,
    runs: list[tuple[str, str, str]],
    date_str: str,
) -> None:
    """Fire-and-forget: schedule ``_monitor_loop`` as a background task.

    Args:
        slack_context: dict with ``client``, ``channel``, ``thread_ts``
        runs: list of ``(location_name, flow_run_id, flow_run_name)``
        date_str: the date being crawled (for display purposes)
    """
    task = asyncio.create_task(_monitor_loop(slack_context, runs, date_str))
    # Prevent the task from being garbage-collected before completion.
    task.add_done_callback(lambda t: _log_task_done(t))
    log.info(
        "background_monitor.started",
        run_count=len(runs),
        date_str=date_str,
    )


def _log_task_done(task: asyncio.Task) -> None:
    if task.exception():
        log.error("background_monitor.task_crashed", exc_info=task.exception())


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

async def _monitor_loop(
    slack_context: dict,
    runs: list[tuple[str, str, str]],
    date_str: str,
) -> None:
    """Poll Prefect for flow-run states and post Slack updates periodically."""
    client = slack_context["client"]
    channel = slack_context["channel"]
    thread_ts = slack_context["thread_ts"]

    # Build status tracking dict: flow_run_id -> info
    statuses: dict[str, dict] = {}
    for location, run_id, run_name in runs:
        statuses[run_id] = {
            "location": location,
            "name": run_name,
            "status": "PENDING",
            "message": None,
        }

    start_time = time.monotonic()
    last_update_time = start_time  # force first update after UPDATE_INTERVAL

    try:
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= MAX_POLL_DURATION:
                await _post_message(
                    client, channel, thread_ts,
                    f"Batch crawl monitor timed out after {MAX_POLL_DURATION // 60} minutes. "
                    f"Some runs may still be in progress.",
                )
                log.warning("background_monitor.timeout", elapsed_s=int(elapsed))
                return

            # Poll all non-terminal runs
            non_terminal_ids = [
                rid for rid, info in statuses.items()
                if info["status"] not in _TERMINAL_STATES
            ]

            if not non_terminal_ids:
                # All done -- post final summary and exit
                summary = _format_final_summary(statuses, date_str)
                await _post_message(client, channel, thread_ts, summary)
                log.info(
                    "background_monitor.complete",
                    completed=sum(1 for s in statuses.values() if s["status"] == "COMPLETED"),
                    failed=sum(1 for s in statuses.values() if s["status"] in ("FAILED", "CANCELLED", "CRASHED")),
                )
                return

            # Fetch statuses in parallel
            tasks = [_safe_get_status(rid) for rid in non_terminal_ids]
            results = await asyncio.gather(*tasks)

            for rid, result in zip(non_terminal_ids, results):
                if result is not None:
                    state = result.get("state", {})
                    statuses[rid]["status"] = state.get("type", "UNKNOWN")
                    statuses[rid]["message"] = state.get("message")

            # Post progress update if enough time has passed
            now = time.monotonic()
            if now - last_update_time >= UPDATE_INTERVAL:
                progress_msg = _format_progress(statuses, date_str)
                await _post_message(client, channel, thread_ts, progress_msg)
                last_update_time = now

            await asyncio.sleep(POLL_INTERVAL)

    except Exception:
        log.error("background_monitor.loop_error", exc_info=True)
        try:
            await _post_message(
                client, channel, thread_ts,
                "Batch crawl monitor encountered an error and stopped. "
                "Check the Prefect dashboard for run statuses.",
            )
        except Exception:
            log.error("background_monitor.error_notification_failed", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _safe_get_status(flow_run_id: str) -> dict | None:
    """Fetch a single flow-run status, returning None on error."""
    try:
        return await prefect_api.get_flow_run_status(flow_run_id)
    except Exception:
        log.warning("background_monitor.poll_error", flow_run_id=flow_run_id, exc_info=True)
        return None


async def _post_message(client, channel: str, thread_ts: str, text: str) -> None:
    """Post a message to the Slack thread, swallowing errors."""
    try:
        await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
    except Exception:
        log.error("background_monitor.slack_post_failed", exc_info=True)


def _format_progress(statuses: dict, date_str: str) -> str:
    """Format an intermediate progress update for Slack."""
    completed = []
    running = []
    failed = []

    for info in statuses.values():
        st = info["status"]
        if st == "COMPLETED":
            completed.append(info["location"])
        elif st in ("FAILED", "CANCELLED", "CRASHED"):
            failed.append(info)
        else:
            running.append(info["location"])

    lines = [
        f"Batch crawl progress ({date_str}):",
        f"Completed: {len(completed)} | Running: {len(running)} | Failed: {len(failed)}",
    ]

    # Show recently finished locations
    recently_done = [info for info in statuses.values() if info["status"] in _TERMINAL_STATES]
    if recently_done:
        lines.append("")
        lines.append("Finished so far:")
        for info in sorted(recently_done, key=lambda i: i["location"]):
            if info["status"] == "COMPLETED":
                lines.append(f"  - {info['location']}: completed")
            else:
                msg = info.get("message") or info["status"]
                lines.append(f"  - {info['location']}: {info['status'].lower()} - {msg}")

    return "\n".join(lines)


def _format_final_summary(statuses: dict, date_str: str) -> str:
    """Format the final summary posted when all runs are terminal."""
    completed = sorted(
        info["location"] for info in statuses.values() if info["status"] == "COMPLETED"
    )
    failed = sorted(
        (info["location"], info.get("message") or info["status"])
        for info in statuses.values()
        if info["status"] in ("FAILED", "CANCELLED", "CRASHED")
    )

    total = len(statuses)

    if not failed:
        return (
            f"Batch crawl complete ({date_str}):\n"
            f"All {total} locations completed successfully."
        )

    lines = [
        f"Batch crawl complete ({date_str}):",
        f"{len(completed)} succeeded | {len(failed)} failed",
    ]

    if completed:
        lines.append(f"\nCompleted ({len(completed)}):")
        for loc in completed:
            lines.append(f"  - {loc}")

    if failed:
        lines.append(f"\nFailed ({len(failed)}):")
        for loc, msg in failed:
            lines.append(f"  - {loc}: {msg}")

    return "\n".join(lines)
