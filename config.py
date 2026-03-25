import os

# These are read at import time. The caller must have loaded .env before importing config.
SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN: str = os.environ.get("SLACK_APP_TOKEN", "")
ALLOWED_USERS: frozenset[str] = frozenset(
    u.strip() for u in os.environ.get("ALLOWED_USERS", "").split(",") if u.strip()
)
ALLOWED_CHANNELS: frozenset[str] = frozenset(
    c.strip() for c in os.environ.get("ALLOWED_CHANNEL", "").split(",") if c.strip()
)

# Bot's own Slack user ID (needed to filter self-mentions in thread replies)
BOT_USER_ID: str = os.environ.get("BOT_USER_ID", "")

# v1.1: MCP server credentials
LINEAR_API_KEY: str = os.environ.get("LINEAR_API_KEY", "")
SENTRY_AUTH_TOKEN: str = os.environ.get("SENTRY_AUTH_TOKEN", "")

# v1.2: mic-transformer MCP server disable override
# Enabled by default when path exists on disk; set to "1"/"true"/"yes" to disable for troubleshooting
MIC_TRANSFORMER_MCP_DISABLED: bool = os.environ.get(
    "MIC_TRANSFORMER_MCP_DISABLED", ""
).lower() in ("1", "true", "yes")

# v1.1: Additional repo directories (comma-separated absolute paths on VM)
# Example: /home/bot/oso-fe-gsnap,/home/bot/irismed-service,/home/bot/oso-desktop
ADDITIONAL_REPOS: list[str] = [
    r.strip()
    for r in os.environ.get("ADDITIONAL_REPOS", "").split(",")
    if r.strip()
]

# v1.9: Memory database path
MEMORY_DB_PATH: str = os.environ.get("MEMORY_DB_PATH", "/home/bot/data/superbot_memory.db")
