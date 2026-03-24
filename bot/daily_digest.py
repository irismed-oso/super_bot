"""
Daily activity digest scheduler.

Posts a summary of yesterday's bot activity to the configured Slack channel
each morning. Runs as an asyncio background task started from app.py.
"""

import asyncio
from datetime import date, datetime, time, timedelta

import structlog

from bot import activity_log
from bot.digest_changelog import build_changelog_section

log = structlog.get_logger(__name__)

DIGEST_HOUR = 8   # 8:00 AM local time
DIGEST_MINUTE = 0


def _format_task_summary(entries: list[dict]) -> str:
    """Format activity entries into the task summary portion of the digest."""
    if not entries:
        return ""

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


async def format_digest(entries: list[dict], target_date: date) -> str:
    """Format activity entries and changelog into a Slack digest message.

    Combines the task summary (from activity log entries) with the
    changelog section (from git activity + cross-check). Returns the
    full digest text ready to post.
    """
    task_summary = _format_task_summary(entries)
    changelog = await build_changelog_section(target_date)

    # Build the full digest
    parts = ["*Daily Digest*"]

    if not task_summary and not changelog:
        parts.append("No activity yesterday.")
    else:
        if task_summary:
            parts.append(task_summary)
        if changelog:
            if task_summary:
                parts.append("")  # blank line separator
            parts.append(changelog)

    return "\n".join(parts)


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
            yesterday = date.today() - timedelta(days=1)
            entries = activity_log.read_yesterday()
            text = await format_digest(entries, yesterday)
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
