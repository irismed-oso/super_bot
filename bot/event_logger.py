"""
Per-turn event logger for agent runs.

Builds an async on_message callback that writes each Claude SDK message
(AssistantMessage text + tool_use, UserMessage tool_result, final
ResultMessage) into the `agent_events` table via bot.db.log_event.

One row per block — turn_index increments per AssistantMessage so a
reader can reconstruct the trace in order.

Gracefully degrades: if bot.db has no pool, nothing is written.
"""

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from bot import db

log = structlog.get_logger(__name__)


def make_event_logger(session_fk: int | None):
    """Return an async on_message callback that persists every block to agent_events.

    session_fk: PK from bot.db.upsert_session; if None, callback is a no-op.
    """
    turn_index = 0

    async def on_message_cb(message):
        nonlocal turn_index
        if session_fk is None:
            return
        try:
            if isinstance(message, AssistantMessage):
                turn_index += 1
                for block in message.content:
                    if isinstance(block, TextBlock):
                        await db.log_event(
                            session_fk, turn_index, "text",
                            payload={"text": block.text},
                        )
                    elif isinstance(block, ToolUseBlock):
                        await db.log_event(
                            session_fk, turn_index, "tool_use",
                            tool_name=block.name,
                            tool_use_id=block.id,
                            payload={"input": block.input},
                        )
            elif isinstance(message, UserMessage):
                for block in getattr(message, "content", []) or []:
                    if isinstance(block, ToolResultBlock):
                        content = block.content
                        if isinstance(content, list):
                            text = "\n".join(
                                c.get("text", "") if isinstance(c, dict) else str(c)
                                for c in content
                            )
                        else:
                            text = str(content) if content is not None else ""
                        await db.log_event(
                            session_fk, turn_index, "tool_result",
                            tool_use_id=block.tool_use_id,
                            payload={
                                "output": text,
                                "is_error": bool(getattr(block, "is_error", False)),
                            },
                        )
            elif isinstance(message, ResultMessage):
                await db.log_event(
                    session_fk, turn_index, "result",
                    payload={
                        "subtype": message.subtype,
                        "num_turns": message.num_turns,
                        "session_id": message.session_id,
                        "result": message.result,
                    },
                )
        except Exception as exc:
            log.warning("event_logger.callback_failed", error=str(exc))

    return on_message_cb
