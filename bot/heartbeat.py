"""
Progress heartbeat for long-running agent sessions.

Edits a single Slack message periodically to show elapsed time,
last activity milestone, and turn count -- a "still alive" signal
so users never wonder whether the bot is stuck.

Timer schedule: first tick at 60s, then every 180s (3 minutes).
"""

import asyncio
import time

import structlog

from bot.agent import MAX_TURNS
from bot.progress import format_elapsed

log = structlog.get_logger(__name__)


class Heartbeat:
    """Manages periodic progress message edits during an agent session."""

    def __init__(self):
        self.turn_count: int = 0
        self.last_activity: str = "Starting up..."
        self._started_at: float = 0.0
        self._progress_msg: dict | None = None
        self._client = None
        self._task: asyncio.Task | None = None
        self._stopped: bool = False

    def start(self, client, progress_msg: dict | None) -> None:
        """Start the heartbeat timer loop.

        Args:
            client: Slack async client for chat_update calls.
            progress_msg: Dict with 'ts' and 'channel' keys for the message to edit.
                          If None, logs a warning and skips (no message to edit).
        """
        if progress_msg is None:
            log.warning("heartbeat.start_skipped_no_msg")
            return
        self._client = client
        self._progress_msg = progress_msg
        self._started_at = time.time()
        self._stopped = False
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the heartbeat timer without editing the progress message.

        Used for cancellation and error paths where the caller handles
        messaging. Idempotent -- safe to call multiple times.
        """
        self._stopped = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def finish(self) -> None:
        """Stop the heartbeat and edit the progress message to show completion.

        Edits the message one final time to show ':white_check_mark: Completed in Xm Ys'.
        Then stops the timer. Idempotent -- if already stopped, skips the edit.
        """
        if self._stopped:
            return
        self._stopped = True

        if self._progress_msg and self._client:
            elapsed = format_elapsed(int(time.time() - self._started_at))
            text = f":white_check_mark: Completed in {elapsed}"
            try:
                await self._client.chat_update(
                    channel=self._progress_msg["channel"],
                    ts=self._progress_msg["ts"],
                    text=text,
                )
                log.info("heartbeat.finish_edited", elapsed=elapsed)
            except Exception:
                log.warning("heartbeat.finish_edit_failed")

        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def format_message(self) -> str:
        """Build the heartbeat-format progress string.

        Format: ':hourglass: Still working... {activity} | Turn X/MAX | Ym Zs'
        """
        elapsed = format_elapsed(int(time.time() - self._started_at))
        return (
            f":hourglass: Still working... {self.last_activity}"
            f" | Turn {self.turn_count}/{MAX_TURNS}"
            f" | {elapsed}"
        )

    async def _loop(self) -> None:
        """Async timer loop: first tick at 60s, then every 180s."""
        try:
            await asyncio.sleep(60)
            if not self._stopped:
                await self._tick()
            while not self._stopped:
                await asyncio.sleep(180)
                if not self._stopped:
                    await self._tick()
        except asyncio.CancelledError:
            return

    async def _tick(self) -> None:
        """Edit the progress message with current heartbeat status."""
        text = self.format_message()
        try:
            await self._client.chat_update(
                channel=self._progress_msg["channel"],
                ts=self._progress_msg["ts"],
                text=text,
            )
            log.info(
                "heartbeat.tick",
                turn_count=self.turn_count,
                last_activity=self.last_activity,
            )
        except Exception:
            log.warning("heartbeat.tick_failed")
