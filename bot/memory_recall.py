"""
Auto-recall: retrieve and inject relevant memories into agent prompts.

Fetches all active rules unconditionally, then fills remaining slots
with BM25-ranked FTS5 search results.  Formats as a prompt block with
category-bracketed lines and a citation footer.

Gracefully degrades -- if memory_store is unavailable, returns None
and never crashes the agent pipeline.
"""

import structlog

from bot import memory_store

log = structlog.get_logger(__name__)

_MAX_MEMORIES = 8
_TOKEN_BUDGET = 500


async def build_recall_block(user_text: str) -> str | None:
    """Build a recalled-memories prompt block for the given user message.

    Returns a formatted string to inject into the agent prompt, or None
    if no memories are available or on error.
    """
    try:
        # 1. Always fetch all rules (non-negotiable institutional knowledge)
        rules = await memory_store.list_all(category="rule")

        # 2. FTS5 search for contextually relevant memories
        search_results = await memory_store.search(user_text, limit=10)

        # De-duplicate: remove any search results already in rules set
        rule_ids = {r["id"] for r in rules}
        search_results = [
            m for m in search_results
            if m["id"] not in rule_ids and m.get("category") != "history"
        ]

        # 3. Cap total memories: rules first, fill remaining with search results
        remaining_slots = max(0, _MAX_MEMORIES - len(rules))
        extras = search_results[:remaining_slots]
        all_memories = rules + extras

        if not all_memories:
            return None

        # 4. Token budget guard (rough estimate: 1 token ~ 4 chars)
        lines = []
        total_tokens = 0
        truncated = False
        for mem in all_memories:
            line = f"- [{mem['category']}] {mem['content']}"
            line_tokens = len(line) // 4
            # Always include rules even if over budget
            if total_tokens + line_tokens > _TOKEN_BUDGET and mem in extras:
                truncated = True
                break
            lines.append(line)
            total_tokens += line_tokens

        if truncated:
            log.warning(
                "memory_recall.truncated",
                total_tokens=total_tokens,
                budget=_TOKEN_BUDGET,
            )

        if not lines:
            return None

        # 5. Format as prompt block with citation footer
        count = len(lines)
        header = "RECALLED MEMORIES (from team knowledge base):"
        footer = f"(Remembered: {count} memories applied)"
        block = "\n".join([header] + lines + ["", footer])
        return block

    except Exception as exc:
        log.warning("memory_recall.build_failed", error=str(exc))
        return None
