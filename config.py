import os

# These are read at import time. The caller must have loaded .env before importing config.
SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN: str = os.environ.get("SLACK_APP_TOKEN", "")
GITLAB_TOKEN: str = os.environ.get("GITLAB_TOKEN", "")
ALLOWED_USERS: frozenset[str] = frozenset(
    u.strip() for u in os.environ.get("ALLOWED_USERS", "").split(",") if u.strip()
)
ALLOWED_CHANNEL: str = os.environ.get("ALLOWED_CHANNEL", "")

# v1.1: MCP server credentials
LINEAR_API_KEY: str = os.environ.get("LINEAR_API_KEY", "")
SENTRY_AUTH_TOKEN: str = os.environ.get("SENTRY_AUTH_TOKEN", "")

# v1.1: Additional repo directories (comma-separated absolute paths on VM)
# Example: /home/bot/oso-fe-gsnap,/home/bot/irismed-service,/home/bot/oso-desktop
ADDITIONAL_REPOS: list[str] = [
    r.strip()
    for r in os.environ.get("ADDITIONAL_REPOS", "").split(",")
    if r.strip()
]
