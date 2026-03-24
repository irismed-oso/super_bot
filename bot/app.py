import asyncio
import os
from dotenv import load_dotenv

# Load .env before importing config or handlers
load_dotenv("/home/bot/.env")

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from bot import handlers, queue_manager, daily_digest, db
import config

app = AsyncApp(token=config.SLACK_BOT_TOKEN)
handlers.register(app)


async def main() -> None:
    # Initialize session database (gracefully degrades if unavailable)
    await db.init()
    # Start the task queue consumer before accepting Slack events
    asyncio.create_task(queue_manager.run_queue_loop())
    # Start daily digest scheduler (posts activity summary each morning)
    # Send digest to the first allowed channel
    if config.ALLOWED_CHANNELS:
        digest_channel = next(iter(config.ALLOWED_CHANNELS))
        asyncio.create_task(
            daily_digest.run_digest_loop(app.client, digest_channel)
        )
    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
