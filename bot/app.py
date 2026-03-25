import asyncio
import os
from dotenv import load_dotenv

# Load .env before importing config or handlers
load_dotenv("/home/bot/.env")

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from bot import handlers, queue_manager, daily_digest, db, memory_store
import config
import structlog

_log = structlog.get_logger(__name__)

app = AsyncApp(token=config.SLACK_BOT_TOKEN)
handlers.register(app)


async def _check_deploy_recovery(client) -> None:
    """Check for pending deploy-state and post 'I'm back' to the original thread."""
    from bot.deploy_state import read_and_clear_deploy_state

    state = read_and_clear_deploy_state()
    if state is None:
        return

    # Get current commit SHA
    proc = await asyncio.create_subprocess_exec(
        "git", "rev-parse", "--short", "HEAD",
        stdout=asyncio.subprocess.PIPE,
        cwd="/home/bot/super_bot",
    )
    stdout, _ = await proc.communicate()
    current_sha = stdout.decode().strip()

    try:
        await client.chat_postMessage(
            channel=state["channel"],
            thread_ts=state["thread_ts"],
            text=f"I'm back, running commit `{current_sha}`.",
        )
        _log.info(
            "deploy_recovery.posted",
            channel=state["channel"],
            pre_sha=state.get("pre_sha"),
            current_sha=current_sha,
        )
    except Exception:
        _log.error("deploy_recovery.post_failed", exc_info=True)


async def main() -> None:
    # Initialize session database (gracefully degrades if unavailable)
    await db.init()
    # Initialize memory store (gracefully degrades if unavailable)
    os.makedirs(os.path.dirname(config.MEMORY_DB_PATH), exist_ok=True)
    await memory_store.init(db_path=config.MEMORY_DB_PATH)
    # Start the task queue consumer before accepting Slack events
    asyncio.create_task(queue_manager.run_queue_loop())
    # Start daily digest scheduler (posts activity summary each morning)
    # Send digest to the first allowed channel
    if config.ALLOWED_CHANNELS:
        digest_channel = next(iter(config.ALLOWED_CHANNELS))
        asyncio.create_task(
            daily_digest.run_digest_loop(app.client, digest_channel)
        )

    # Schedule deploy-state recovery after Socket Mode connects
    async def _delayed_deploy_check():
        await asyncio.sleep(5)  # wait for Socket Mode connection
        await _check_deploy_recovery(app.client)

    asyncio.create_task(_delayed_deploy_check())

    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
