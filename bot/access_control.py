from config import ALLOWED_USERS, ALLOWED_CHANNELS


def is_allowed(user_id: str) -> bool:
    """Return True if user_id is in the ALLOWED_USERS set. False if user_id is empty."""
    if not user_id:
        return False
    return user_id in ALLOWED_USERS


def is_allowed_channel(channel_id: str) -> bool:
    """Return True if channel_id is in ALLOWED_CHANNELS, or if no channels configured (permissive fallback)."""
    if not ALLOWED_CHANNELS:
        return True
    return channel_id in ALLOWED_CHANNELS


def is_bot_message(event: dict) -> bool:
    """Return True if the event is from a bot (self or other). Checks both bot_id and subtype fields.
    This prevents the infinite loop where the bot responds to its own messages."""
    return bool(event.get("bot_id")) or event.get("subtype") == "bot_message"
