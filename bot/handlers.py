import re

from slack_bolt.app.async_app import AsyncApp
from bot.access_control import is_allowed, is_allowed_channel, is_bot_message
from bot.deduplication import is_seen, mark_seen
from bot import task_state, formatter, worktree, progress, session_map, activity_log
from bot.queue_manager import QueuedTask, enqueue, queue_depth


def _build_prompt(
    user_text: str,
    worktree_path: str | None,
    channel: str,
    thread_ts: str,
) -> str:
    """Construct the agent prompt with operational context injected."""
    ts_nodot = thread_ts.replace(".", "")
    slack_link = f"https://slack.com/archives/{channel}/p{ts_nodot}"
    lines = [user_text]
    if worktree_path:
        lines += [
            "",
            f"Working directory for this task: {worktree_path}",
            "This is an isolated git worktree. Commit your changes to this worktree's branch.",
            "When creating an MR, target the 'develop' branch.",
            "MR description MUST include all four of the following sections:",
            "  1. What was changed -- a brief summary of the change and its purpose",
            "  2. Files changed -- a list of every file you created or modified",
            "  3. Test results -- the pytest output (or 'No tests run' if tests were not relevant)",
            f"  4. Slack thread link: {slack_link}",
        ]
    return "\n".join(lines)


def register(app: AsyncApp) -> None:
    """Register all event and command handlers on the given app."""

    async def _run_agent_real(body, client, event):
        """Wire Slack event to the real agent stack with worktree isolation and progress."""
        import structlog
        log = structlog.get_logger()

        thread_ts = event.get("thread_ts") or event["ts"]
        channel = event["channel"]
        text = event.get("text", "")
        user_id = event.get("user", "")
        clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        session_id = session_map.get(channel, thread_ts)
        is_code_task_flag = worktree.is_code_task(clean_text)
        worktree_path_val = None

        if session_id:
            # Resuming an existing session -- must use the same CWD
            stored_cwd = session_map.get_cwd(channel, thread_ts)
            if stored_cwd:
                worktree_path_val = stored_cwd
        elif is_code_task_flag:
            # New session with code task -- create a worktree
            try:
                worktree_path_val = await worktree.create(thread_ts, clean_text)
            except Exception as exc:
                log.error("worktree_create_failed", error=str(exc))
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=formatter.format_error("Failed to create worktree", str(exc)),
                )
                return
        prompt = _build_prompt(clean_text, worktree_path_val, channel, thread_ts)
        on_message_cb = progress.make_on_message(client, channel, thread_ts)

        async def notify_cb():
            await progress.post_started(client, channel, thread_ts, clean_text)

        task_started_at = __import__("time").time()

        async def result_cb(result: dict):
            # Persist session + CWD for thread continuity
            if result.get("session_id"):
                session_map.set(channel, thread_ts, result["session_id"], cwd=worktree_path_val)
            # On failure, stash uncommitted worktree changes
            error_subtypes = {"error_timeout", "error_cancelled", "error_internal"}
            if result.get("subtype") in error_subtypes:
                await worktree.stash(thread_ts)
            await progress.post_result(client, channel, thread_ts, result, is_code_task_flag)
            # Log activity for daily digest
            activity_log.append({
                "ts": thread_ts,
                "user": user_id,
                "text": clean_text[:200],
                "subtype": result.get("subtype", "unknown"),
                "num_turns": result.get("num_turns", 0),
                "duration_s": int(__import__("time").time() - task_started_at),
                "channel": channel,
                "thread_ts": thread_ts,
            })

        task = QueuedTask(
            prompt=prompt,
            session_id=session_id,
            channel=channel,
            thread_ts=thread_ts,
            user_id=user_id,
            cwd=worktree_path_val,
            notify_callback=notify_cb,
            result_callback=result_cb,
            on_message=on_message_cb,
        )

        if not enqueue(task):
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=formatter.format_queue_full(queue_depth(), clean_text),
            )

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
        asyncio.create_task(_run_agent_real(body, client, event))

    @app.command("/sb-status")
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
            "*/sb-status* -- current task, recent history, uptime\n"
            "*/cancel* -- stop the currently running task (confirm step in Phase 2)\n"
            "*/help* -- this message"
        )
