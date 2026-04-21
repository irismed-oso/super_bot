import asyncio
import re

from slack_bolt.app.async_app import AsyncApp
from bot.access_control import is_allowed, is_allowed_channel, is_bot_message
from bot.deduplication import is_seen, mark_seen
from bot import task_state, formatter, worktree, progress, session_map, activity_log, git_activity, db, event_logger
from bot.heartbeat import Heartbeat
from bot.queue_manager import QueuedTask, enqueue, queue_depth
from bot.deploy_state import resolve_repo
from bot.deploy import handle_deploy
from bot.rollback import handle_rollback
from bot.fast_commands import try_fast_command
from bot import memory_recall
from bot import thread_scanner
from config import BOT_USER_ID

_DEPLOY_CMD_RE = re.compile(
    r"deploy\s+(?:force\s+)?(\S+)\s*$",
    re.IGNORECASE,
)

_ROLLBACK_CMD_RE = re.compile(
    r"rollback\s+(?:force\s+)?(\S+)(?:\s+([a-f0-9]{4,40}))?\s*$",
    re.IGNORECASE,
)


_AGENT_RULES = """
RULES (apply to every task):
- When asked to change output, behavior, or add/remove fields: modify the FUNCTIONAL CODE
  that produces the output, NOT just docstrings, comments, or type hints.
- Verify your change works by tracing the code path from input to output.
- If the user says "I don't see X" or "X is missing", that means the runtime output is wrong.
  Find the code that generates that output and fix it there.
- Never update only documentation/docstrings when the user is reporting a functional gap.
- For log requests: run `python -m bot.log_tools journald <service> [--lines N] [--grep PATTERN] [--since TIMESPEC]`
  or `python -m bot.log_tools prefect <run-id-or-name>`. Output is auto-parsed and truncated.
  Services: superbot (sb), mic (mic_transformer, mt). Default 50 lines.
- When the user asks about "pipeline status", "flow runs", or "what ran today": run `python -m bot.pipeline_status` with appropriate flags. Use --hours N for relative windows or --since YYYY-MM-DD for specific dates. Default (no flags) shows last 24 hours.
- When the user wants to update portal credentials for a location, tell them to use:
  `update creds <eyemed|vsp> <location> <username> <password>`
  This is a fast-path command that writes directly to GCP Secret Manager.
- When the user asks to READ portal credentials (e.g. "what's the VSP login for MSOC", "get creds vsp Beverly", "MSOC VSP password"), tell them to use:
  `get creds <eyemed|vsp> <location>`
  This fast-path reads from GCP Secret Manager and is the ONLY correct source.
  Never read `config/payer_logins.csv` or `config/eyemed_payer_logins.csv` in the mic_transformer repo to answer credential questions -- the CSV is a stale fallback, and GCP Secret Manager is authoritative. Never repeat a credential you saw earlier in the thread or remembered from a previous task -- always direct the user at `get creds` so they get the live value.
""".strip()


def _build_prompt(
    user_text: str,
    worktree_path: str | None,
    channel: str,
    thread_ts: str,
    recall_block: str | None = None,
) -> str:
    """Construct the agent prompt with operational context injected."""
    ts_nodot = thread_ts.replace(".", "")
    slack_link = f"https://slack.com/archives/{channel}/p{ts_nodot}"
    lines = [user_text]
    if recall_block:
        lines += ["", recall_block]
    lines += ["", _AGENT_RULES]
    if worktree_path:
        lines += [
            "",
            f"Working directory for this task: {worktree_path}",
            "This is an isolated git worktree. Commit your changes to this worktree's branch.",
            "When creating a PR, target the 'develop' branch.",
            "PR description MUST include all four of the following sections:",
            "  1. What was changed -- a brief summary of the change and its purpose",
            "  2. Files changed -- a list of every file you created or modified",
            "  3. Test results -- the pytest output (or 'No tests run' if tests were not relevant)",
            f"  4. Slack thread link: {slack_link}",
        ]
    return "\n".join(lines)


def register(app: AsyncApp) -> None:
    """Register all event and command handlers on the given app."""

    async def _run_agent_real(body, client, event, ack_ts=None):
        """Wire Slack event to the real agent stack with worktree isolation and progress."""
        import structlog
        log = structlog.get_logger()

        thread_ts = event.get("thread_ts") or event["ts"]
        channel = event["channel"]
        text = event.get("text", "")
        user_id = event.get("user", "")
        clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        # DB: upsert session and log user input
        db_session_fk = await db.upsert_session(channel, thread_ts, user_id)
        await db.log_message(db_session_fk, "user_input", clean_text, slack_ts=event["ts"])

        # Fast-path commands (memory, deploy guard, rollback guard)
        slack_context = {"client": client, "channel": channel, "thread_ts": thread_ts, "user_id": user_id}
        fast_result = await try_fast_command(clean_text, slack_context=slack_context)
        if fast_result is not None:
            ts_to_edit = ack_ts or thread_ts
            try:
                await client.chat_update(channel=channel, ts=ts_to_edit, text=fast_result)
            except Exception:
                await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=fast_result)
            return

        # Deploy command routing -- handled outside the agent queue
        if _DEPLOY_CMD_RE.search(clean_text):
            resolved = resolve_repo(clean_text)
            if resolved is None:
                msg = "Unknown repo. Available: super_bot, mic_transformer"
                if ack_ts:
                    await client.chat_update(channel=channel, ts=ack_ts, text=msg)
                else:
                    await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=msg)
                return
            repo_name, repo_config = resolved
            await handle_deploy(
                repo_name, repo_config, client, channel,
                thread_ts, user_id, ack_ts=ack_ts,
            )
            return

        # Rollback command routing -- handled outside the agent queue
        rollback_match = _ROLLBACK_CMD_RE.search(clean_text)
        if rollback_match:
            sha_match = rollback_match.group(2)  # optional target SHA
            resolved = resolve_repo(clean_text)
            if resolved is None:
                msg = "Unknown repo. Available: super_bot, mic_transformer"
                if ack_ts:
                    await client.chat_update(channel=channel, ts=ack_ts, text=msg)
                else:
                    await client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=msg)
                return
            repo_name, repo_config = resolved
            await handle_rollback(
                repo_name, repo_config, client, channel,
                thread_ts, user_id, ack_ts=ack_ts, target_sha=sha_match,
            )
            return

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
        # Auto-recall: inject relevant memories into agent prompt
        recall_block = await memory_recall.build_recall_block(clean_text)
        if recall_block:
            mem_count = sum(1 for ln in recall_block.splitlines() if ln.startswith("- ["))
            log.info("memory_recall.injected", memories_count=mem_count, prompt_len=len(recall_block))

        prompt = _build_prompt(clean_text, worktree_path_val, channel, thread_ts, recall_block=recall_block)
        progress_msg = None
        _inner_cb = None
        heartbeat = Heartbeat()

        async def notify_cb():
            nonlocal progress_msg, _inner_cb
            progress_msg = await progress.post_started(client, channel, thread_ts, clean_text)
            heartbeat.start(client, progress_msg)
            _inner_cb = progress.make_on_message(client, channel, thread_ts, progress_msg, heartbeat=heartbeat)

        _event_log_cb = event_logger.make_event_logger(db_session_fk)

        async def on_message_cb(message):
            if _inner_cb:
                await _inner_cb(message)
            await _event_log_cb(message)

        task_started_at = __import__("time").time()

        async def result_cb(result: dict):
            # Stop heartbeat: finish() for normal completion, stop() for errors
            error_subtypes = {"error_timeout", "error_cancelled", "error_internal"}
            if result.get("subtype") in error_subtypes:
                await heartbeat.stop()
            else:
                await heartbeat.finish()
            # Persist session + CWD for thread continuity
            if result.get("session_id"):
                session_map.set(channel, thread_ts, result["session_id"], cwd=worktree_path_val)
                await db.upsert_session(channel, thread_ts, user_id, session_id=result["session_id"])
            # On failure, stash uncommitted worktree changes
            if result.get("subtype") in error_subtypes:
                await worktree.stash(thread_ts)
            duration_s = int(__import__("time").time() - task_started_at)
            result["task_text"] = clean_text
            await progress.post_result(client, channel, thread_ts, result, is_code_task_flag, duration_s=duration_s)
            # DB: log bot output and execution metadata
            bot_output = result.get("result") or ""
            if result.get("partial_texts"):
                bot_output = "\n---\n".join(result["partial_texts"])
            await db.log_message(db_session_fk, "bot_output", bot_output)
            error_text = result.get("result") if result.get("subtype", "").startswith("error") else None
            await db.log_execution(
                db_session_fk,
                prompt=clean_text,
                duration_secs=float(duration_s),
                num_turns=result.get("num_turns"),
                subtype=result.get("subtype"),
                result_text=result.get("result"),
                error=error_text,
            )
            # Log activity for daily digest
            activity_log.append({
                "ts": thread_ts,
                "user": user_id,
                "text": clean_text[:200],
                "subtype": result.get("subtype", "unknown"),
                "num_turns": result.get("num_turns", 0),
                "duration_s": duration_s,
                "channel": channel,
                "thread_ts": thread_ts,
            })
            # Capture git commits and PRs for changelog
            try:
                await git_activity.capture_git_activity(
                    result=result,
                    cwd=worktree_path_val,
                    channel=channel,
                    thread_ts=thread_ts,
                )
            except Exception as exc:
                log.warning("git_activity.capture_failed", error=str(exc))
            # Auto-scan thread for memorable information (fire-and-forget)
            if result.get("subtype") not in error_subtypes:
                task_summary = f"Task: {clean_text[:150]} | Result: {result.get('subtype', 'success')}"
                asyncio.create_task(
                    thread_scanner.scan_and_store(
                        client=client,
                        channel=channel,
                        thread_ts=thread_ts,
                        user_id=user_id,
                        task_summary=task_summary,
                    )
                )

        task = QueuedTask(
            prompt=prompt,
            session_id=session_id,
            channel=channel,
            thread_ts=thread_ts,
            user_id=user_id,
            clean_text=clean_text,
            cwd=worktree_path_val,
            notify_callback=notify_cb,
            result_callback=result_cb,
            on_message=on_message_cb,
            heartbeat=heartbeat,
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
        ack_resp = await client.chat_postMessage(
            channel=event["channel"],
            thread_ts=thread_ts,
            text="Working on it."
        )
        ack_ts = ack_resp["ts"]

        # Fire agent work in background
        asyncio.create_task(_run_agent_real(body, client, event, ack_ts=ack_ts))

    @app.event("message")
    async def handle_thread_reply(body, client, event):
        import asyncio
        import structlog
        log = structlog.get_logger()

        # Only process threaded replies (not top-level channel messages)
        thread_ts = event.get("thread_ts")
        if not thread_ts or thread_ts == event.get("ts"):
            return

        # Skip subtypes (channel_join, bot_message, message_changed, etc.)
        if event.get("subtype"):
            return

        # Only respond in threads where bot has an active session
        channel = event.get("channel", "")
        if not session_map.get(channel, thread_ts):
            return

        # Skip bot's own messages
        if is_bot_message(event):
            return

        # Skip @mentions -- already handled by handle_mention
        text = event.get("text", "")
        if BOT_USER_ID and f"<@{BOT_USER_ID}>" in text:
            return

        # Access control
        user_id = event.get("user", "")
        if not is_allowed(user_id):
            return
        if not is_allowed_channel(channel):
            return

        # Dedup
        event_id = body.get("event_id", "")
        if event_id and is_seen(event_id):
            return
        if event_id:
            mark_seen(event_id)

        log.info("thread_reply_received", channel=channel, thread_ts=thread_ts)

        # Acknowledge and process
        await client.reactions_add(
            channel=channel,
            name="hourglass_flowing_sand",
            timestamp=event["ts"],
        )
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
