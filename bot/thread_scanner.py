"""
Post-session thread scanner for SuperBot.

After an agent session completes, scans the thread for memorable
directives and facts, extracts them via a lightweight Claude API call,
deduplicates against existing memories, and stores new ones.

Also captures a one-line task history summary for every completed session.

Runs as a fire-and-forget asyncio.create_task -- failures are logged
but never propagate.
"""

import structlog

from bot import memory_store

log = structlog.get_logger(__name__)

# Lazy-init Anthropic client -- bot runs without it
_anthropic_client = None

_EXTRACTION_MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """\
You extract memorable facts and directives from Slack conversations.

Rules:
- ONLY extract explicit directives: statements containing "always", "never", "the rule is", "make sure to", "don't forget", "from now on", or similar imperative language
- ONLY extract stated facts: concrete information like names, dates, configurations, procedures, preferences
- DO NOT extract: questions, speculative statements ("maybe", "I think", "could be"), bot instructions, pleasantries, status updates about current tasks, temporary context
- DO NOT extract anything that is just describing what the bot should do RIGHT NOW for this specific task
- Return each extracted memory on its own line, one per line
- If nothing is worth remembering, return exactly: NONE
- Keep each memory concise (1-2 sentences max)
- Do not number the lines"""


def _get_anthropic_client():
    """Lazy-initialize the async Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        try:
            import anthropic

            _anthropic_client = anthropic.AsyncAnthropic()
        except ImportError:
            log.warning("thread_scanner.anthropic_not_installed")
            return None
    return _anthropic_client


async def scan_and_store(
    client,
    channel: str,
    thread_ts: str,
    user_id: str,
    task_summary: str,
) -> None:
    """Scan a completed thread for memorable information and store task history.

    This is the fire-and-forget entry point called from result_cb.
    The entire body is wrapped in try/except -- failures must never propagate
    since this runs as a detached background task.
    """
    try:
        # Step 1: Store task history immediately
        await _store_task_history(task_summary, user_id, channel)

        # Step 2: Fetch thread messages
        resp = await client.conversations_replies(
            channel=channel, ts=thread_ts, limit=100
        )
        messages = resp.get("messages", [])

        # Step 3: Filter to human messages only
        human_messages = [
            msg
            for msg in messages
            if not msg.get("bot_id") and not msg.get("subtype")
        ]

        # Step 4: If no human messages, return early
        if not human_messages:
            log.info("thread_scanner.no_human_messages", channel=channel)
            return

        # Step 5: Build extraction input
        text_block = "\n".join(
            f"{i}. {msg['text']}" for i, msg in enumerate(human_messages, 1)
        )

        # Step 6: Extract memories via Claude
        extracted = await _extract_memories(text_block)
        if not extracted:
            log.info("thread_scanner.nothing_extracted", channel=channel)
            return

        # Step 7: Deduplicate and store
        stored_count = 0
        for item in extracted:
            existing = await memory_store.search(item, limit=3)
            if _is_duplicate(item, existing):
                continue
            category = memory_store.categorize(item)
            await memory_store.store(
                content=item,
                category=category,
                source_user=user_id,
                source_channel=channel,
            )
            stored_count += 1

        # Step 8: Log results
        log.info(
            "thread_scanner.complete",
            extracted=len(extracted),
            stored=stored_count,
            channel=channel,
        )
    except Exception as exc:
        log.warning("thread_scanner.scan_failed", error=str(exc))


def _is_duplicate(item: str, existing: list[dict]) -> bool:
    """Check if item is a near-duplicate of any existing memory.

    Uses simple substring similarity -- if the extracted item is a substring
    of existing content or vice versa, it's considered a duplicate.
    """
    item_lower = item.lower().strip()
    for row in existing:
        existing_lower = row.get("content", "").lower().strip()
        if not existing_lower:
            continue
        # Substring check in both directions
        if item_lower in existing_lower or existing_lower in item_lower:
            return True
    return False


async def _extract_memories(human_text: str) -> list[str]:
    """Extract memorable information from conversation text via Claude API.

    Returns a list of extracted strings, or empty list if nothing worth
    remembering or if the API call fails.
    """
    anthropic_client = _get_anthropic_client()
    if anthropic_client is None:
        log.warning("thread_scanner.no_anthropic_client")
        return []

    user_msg = (
        f"Extract memorable information from this conversation:\n\n{human_text}"
    )

    try:
        response = await anthropic_client.messages.create(
            model=_EXTRACTION_MODEL,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw_text = response.content[0].text.strip()
    except Exception as exc:
        log.warning("thread_scanner.extraction_failed", error=str(exc))
        return []

    # Parse response
    if raw_text.upper() == "NONE" or not raw_text:
        return []

    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    return lines


async def _store_task_history(
    summary: str, user_id: str, channel: str
) -> None:
    """Store a one-line task history summary with category='history'."""
    await memory_store.store(
        content=summary,
        category="history",
        source_user=user_id,
        source_channel=channel,
    )
    log.info("thread_scanner.task_history_stored", summary=summary[:100])
