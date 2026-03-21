"""
Daily activity digest scheduler.

Posts a summary of yesterday's bot activity to the configured Slack channel
each morning. Runs as an asyncio background task started from app.py.
"""

import asyncio
from datetime import datetime, time, timedelta

import structlog

from bot import activity_log

log = structlog.get_logger(__name__)

DIGEST_HOUR = 8   # 8:00 AM local time
DIGEST_MINUTE = 0


def format_digest(entries: list[dict]) -> str:
    """Format activity entries into a Slack digest message."""
    if not entries:
        return "*Daily Digest*\nNo activity yesterday."

    total = len(entries)
    successes = sum(1 for e in entries if e.get("subtype") == "end_turn")
    errors = sum(1 for e in entries if e.get("subtype", "").startswith("error"))
    total_turns = sum(e.get("num_turns", 0) for e in entries)
    total_duration = sum(e.get("duration_s", 0) for e in entries)

    # Group by user
    by_user: dict[str, int] = {}
    for e in entries:
        user = e.get("user", "unknown")
        by_user[user] = by_user.get(user, 0) + 1

    lines = [
        "*Daily Digest*",
        f"Tasks: {total} ({successes} succeeded, {errors} errors)",
        f"Total turns: {total_turns} | Total time: {total_duration // 60}m {total_duration % 60}s",
    ]

    if len(by_user) > 1:
        user_parts = [f"<@{uid}>: {count}" for uid, count in by_user.items()]
        lines.append(f"By user: {', '.join(user_parts)}")

    # List tasks (max 10)
    lines.append("")
    for entry in entries[:10]:
        text = entry.get("text", "")[:80]
        subtype = entry.get("subtype", "unknown")
        icon = "white_check_mark" if subtype == "end_turn" else "x"
        lines.append(f":{icon}: {text}")

    if total > 10:
        lines.append(f"_...and {total - 10} more_")

    return "\n".join(lines)


def _seconds_until_next_digest() -> float:
    """Return seconds until next digest time."""
    now = datetime.now()
    target = datetime.combine(now.date(), time(DIGEST_HOUR, DIGEST_MINUTE))
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_digest_loop(client, channel: str) -> None:
    """Background loop that posts daily digest at DIGEST_HOUR:DIGEST_MINUTE."""
    log.info("digest_loop.started", hour=DIGEST_HOUR, minute=DIGEST_MINUTE)

    while True:
        wait = _seconds_until_next_digest()
        log.info("digest_loop.sleeping", seconds=int(wait))
        await asyncio.sleep(wait)

        try:
            entries = activity_log.read_yesterday()
            text = format_digest(entries)
            await client.chat_postMessage(channel=channel, text=text)
            log.info("digest_loop.posted", entry_count=len(entries))

            # Housekeeping: clean old logs
            removed = activity_log.cleanup_old(keep_days=30)
            if removed:
                log.info("digest_loop.cleanup", removed=removed)
        except Exception as exc:
            log.error("digest_loop.error", error=str(exc))

        # Sleep a bit to avoid double-posting if loop resumes quickly
        await asyncio.sleep(60)
