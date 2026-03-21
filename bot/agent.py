"""
Claude Agent SDK wrapper with timeout and session capture.

Provides run_agent() for direct invocation and run_agent_with_timeout()
for wall-clock-limited execution. Both return a result dict with
session_id, result, subtype, num_turns, and partial_texts.

Key design decisions (from CONTEXT.md / RESEARCH.md):
- MIC_TRANSFORMER_CWD resolved via os.path.realpath() to prevent cwd drift
- Always uses explicit resume=session_id (never continue_conversation=True)
- permission_mode="bypassPermissions" for headless non-interactive execution
- session_id=None is valid for new sessions
"""

import asyncio
import os

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

import config

log = structlog.get_logger(__name__)

# Constant CWD -- must match on every call or session resume silently
# starts fresh (Pitfall 1 in RESEARCH.md). os.path.realpath() resolves
# symlinks so the encoded path is always identical.
MIC_TRANSFORMER_CWD = os.path.realpath(
    os.environ.get("MIC_TRANSFORMER_CWD", "/home/bot/mic_transformer")
)

TIMEOUT_SECONDS = 600   # 10 minutes -- locked decision (CONTEXT.md Safety Limits)
MAX_TURNS = 25          # locked decision (CONTEXT.md Safety Limits)


def _build_mcp_servers() -> dict:
    """Build MCP server config dict from available credentials."""
    servers = {}

    if config.LINEAR_API_KEY:
        servers["linear"] = {
            "command": "npx",
            "args": ["-y", "@anthropic/linear-mcp@latest"],
            "env": {"LINEAR_API_KEY": config.LINEAR_API_KEY},
        }

    if config.SENTRY_AUTH_TOKEN:
        servers["sentry"] = {
            "command": "npx",
            "args": ["-y", "@sentry/mcp-server@latest"],
            "env": {"SENTRY_AUTH_TOKEN": config.SENTRY_AUTH_TOKEN},
        }

    return servers


def _build_add_dirs() -> list[str]:
    """Build list of additional repo directories from config."""
    dirs = []
    for repo_path in config.ADDITIONAL_REPOS:
        real = os.path.realpath(repo_path)
        if os.path.isdir(real):
            dirs.append(real)
        else:
            log.warning("add_dirs.skip_missing", path=real)
    return dirs


async def run_agent(
    prompt: str,
    session_id: str | None,
    *,
    cwd: str | None = None,
    on_text=None,
    on_message=None,
    max_turns: int = MAX_TURNS,
) -> dict:
    """
    Run a Claude agent task and capture the session result.

    Args:
        prompt: The user's prompt text.
        session_id: Session ID to resume, or None for a new session.
        cwd: Optional working directory override (e.g. worktree path).
             Defaults to MIC_TRANSFORMER_CWD when None.
        on_text: Optional async callback invoked with each AssistantMessage text.
        on_message: Optional async callback invoked with the full AssistantMessage
                    object (enables ToolUseBlock inspection for milestone detection).
        max_turns: Maximum conversation turns (default 25).

    Returns:
        dict with keys: session_id, result, subtype, num_turns, partial_texts
    """
    effective_cwd = os.path.realpath(cwd) if cwd else MIC_TRANSFORMER_CWD
    mcp_servers = _build_mcp_servers()
    add_dirs = _build_add_dirs()

    log.info(
        "agent.run_start",
        prompt_preview=prompt[:80],
        session_id=session_id,
        cwd=effective_cwd,
        max_turns=max_turns,
        mcp_server_count=len(mcp_servers),
        add_dir_count=len(add_dirs),
    )

    options = ClaudeAgentOptions(
        cwd=effective_cwd,
        resume=session_id,          # None for new session, str for resume
        max_turns=max_turns,
        permission_mode="bypassPermissions",
        mcp_servers=mcp_servers,
        add_dirs=add_dirs,
    )

    new_session_id = session_id
    result_text = None
    subtype = "unknown"
    num_turns = 0
    partial_texts = []

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            text_parts = [
                b.text for b in message.content if isinstance(b, TextBlock)
            ]
            if text_parts:
                combined = "\n".join(text_parts)
                partial_texts.append(combined)
                if on_text:
                    await on_text(combined)
            if on_message:
                await on_message(message)
        elif isinstance(message, ResultMessage):
            new_session_id = message.session_id
            result_text = message.result
            subtype = message.subtype
            num_turns = message.num_turns

    log.info(
        "agent.run_end",
        subtype=subtype,
        num_turns=num_turns,
        session_id=new_session_id,
    )

    return {
        "session_id": new_session_id,
        "result": result_text,
        "subtype": subtype,
        "num_turns": num_turns,
        "partial_texts": partial_texts,
    }


async def run_agent_with_timeout(
    prompt: str,
    session_id: str | None,
    *,
    cwd: str | None = None,
    on_text=None,
    on_message=None,
    timeout_seconds: int = TIMEOUT_SECONDS,
    max_turns: int = MAX_TURNS,
) -> dict:
    """
    Run a Claude agent task with a wall-clock timeout.

    Wraps run_agent() in asyncio.wait_for(). On timeout, returns a result
    dict with subtype="error_timeout" and retains the prior session_id so
    the caller can still resume the session.

    Args:
        prompt: The user's prompt text.
        session_id: Session ID to resume, or None for a new session.
        cwd: Optional working directory override (e.g. worktree path).
        on_text: Optional async callback invoked with each AssistantMessage text.
        on_message: Optional async callback invoked with the full AssistantMessage.
        timeout_seconds: Wall-clock timeout in seconds (default 600).
        max_turns: Maximum conversation turns (default 25).

    Returns:
        dict with keys: session_id, result, subtype, num_turns, partial_texts
    """
    try:
        return await asyncio.wait_for(
            run_agent(
                prompt,
                session_id,
                cwd=cwd,
                on_text=on_text,
                on_message=on_message,
                max_turns=max_turns,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        log.warning(
            "agent.timeout",
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )
        return {
            "session_id": session_id,   # Retain prior session_id -- can still resume
            "result": None,
            "subtype": "error_timeout",
            "num_turns": -1,
            "partial_texts": [],
        }
