from slack_bolt.app.async_app import AsyncApp
from bot.access_control import is_allowed, is_allowed_channel, is_bot_message
from bot.deduplication import is_seen, mark_seen
from bot import task_state, formatter


def register(app: AsyncApp) -> None:
    """Register all event and command handlers on the given app."""

    async def _run_agent_stub(body, client, event):
        """Phase 1 stub -- Phase 2 replaces this with real Claude Agent SDK invocation."""
        import structlog
        log = structlog.get_logger()
        thread_ts = event.get("thread_ts") or event["ts"]
        channel = event["channel"]
        text = event.get("text", "")
        log.info("agent_stub_called", channel=channel, thread_ts=thread_ts, text_preview=text[:80])
        # Record task in state
        await task_state.set_current({"text": text, "user": event.get("user", ""), "ts": event["ts"]})
        # Post stub completion -- Phase 2 replaces this
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="[Phase 1 -- agent not yet connected. Phase 2 will wire Claude Code here.]"
        )
        await task_state.clear_current()

    @app.event("app_mention")
    async def handle_mention(body, client, event):
        import asyncio
        import structlog
        log = structlog.get_logger()
        log.info("app_mention_received", slack_event=event)

        # Guard 1: Filter bot's own messages (SLCK-04)
        if is_bot_message(event):
            log.info("filtered_bot_message")
            return

        # Guard 2: Event deduplication (SLCK-06)
        event_id = body.get("event_id", "")
        if event_id and is_seen(event_id):
            return

        # Guard 3: Access control (SLCK-03)
        user_id = event.get("user", "")
        if not is_allowed(user_id):
            log.info("filtered_unauthorized_user", user_id=user_id)
            return

        # Guard 4: Channel filter
        channel_id = event.get("channel", "")
        if not is_allowed_channel(channel_id):
            log.info("filtered_channel", channel_id=channel_id)
            return

        # All guards passed -- mark as seen
        if event_id:
            mark_seen(event_id)

        # Immediate acknowledgment to user
        await client.reactions_add(
            channel=event["channel"],
            name="hourglass_flowing_sand",
            timestamp=event["ts"]
        )
        thread_ts = event.get("thread_ts") or event["ts"]
        await client.chat_postMessage(
            channel=event["channel"],
            thread_ts=thread_ts,
            text="Working on it."
        )

        # Fire agent work in background
        asyncio.create_task(_run_agent_stub(body, client, event))

    @app.command("/status")
    async def handle_status(ack, respond):
        await ack()
        current = task_state.get_current()
        recent = task_state.get_recent(5)
        uptime = task_state.get_uptime()
        await respond(formatter.format_status(current, recent, uptime))

    @app.command("/cancel")
    async def handle_cancel(ack, respond):
        await ack()
        current = task_state.get_current()
        if not current:
            await respond("Nothing is running.")
            return
        elapsed = int(__import__("time").time() - current["started_at"])
        await respond(
            f"Running ({elapsed}s): _{current['text'][:100]}_\n"
            "To stop it, reply `/cancel confirm` -- not yet implemented in Phase 1."
        )

    @app.command("/help")
    async def handle_help(ack, respond):
        await ack()
        await respond(
            "*SuperBot* -- autonomous coding assistant for mic_transformer\n"
            "@mention me with a task and I will run Claude Code on it.\n"
            "*/status* -- current task, recent history, uptime\n"
            "*/cancel* -- stop the currently running task (confirm step in Phase 2)\n"
            "*/help* -- this message"
        )
