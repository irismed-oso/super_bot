import os

# These are read at import time. The caller must have loaded .env before importing config.
SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN: str = os.environ.get("SLACK_APP_TOKEN", "")
GITLAB_TOKEN: str = os.environ.get("GITLAB_TOKEN", "")
ALLOWED_USERS: frozenset[str] = frozenset(
    u.strip() for u in os.environ.get("ALLOWED_USERS", "").split(",") if u.strip()
)
ALLOWED_CHANNEL: str = os.environ.get("ALLOWED_CHANNEL", "")
