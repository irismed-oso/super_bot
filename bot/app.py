import asyncio
import os
from dotenv import load_dotenv

# Load .env before importing config or handlers
load_dotenv("/home/bot/.env")

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from bot import handlers, queue_manager
import config

app = AsyncApp(token=config.SLACK_BOT_TOKEN)
handlers.register(app)


async def main() -> None:
    # Start the task queue consumer before accepting Slack events
    asyncio.create_task(queue_manager.run_queue_loop())
    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
