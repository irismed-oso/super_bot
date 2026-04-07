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
    ProcessError,
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

TIMEOUT_SECONDS = 1800  # 30 minutes
MAX_TURNS = 25          # locked decision (CONTEXT.md Safety Limits)


def _build_mcp_servers() -> dict:
    """Build MCP server config dict from available credentials."""
    servers = {}

    # mic-transformer pipeline tools (eyemed_status, vsp_status, etc.)
    mcp_server_script = os.path.join(
        MIC_TRANSFORMER_CWD, ".claude", "mcp", "mic-transformer", "server.py"
    )
    mcp_python = os.path.join(MIC_TRANSFORMER_CWD, ".venv", "bin", "python")

    if config.MIC_TRANSFORMER_MCP_DISABLED:
        log.info("mcp.mic_transformer_disabled_by_env")
    elif os.path.isfile(mcp_server_script) and os.path.isfile(mcp_python):
        servers["mic-transformer"] = {
            "command": mcp_python,
            "args": [mcp_server_script],
        }
    else:
        log.warning(
            "mcp.mic_transformer_missing",
            script=mcp_server_script,
            python=mcp_python,
        )

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


def _format_error_detail(
    exc: BaseException,
    stderr_output: str,
    cwd: str,
    *,
    exit_code: int | None,
) -> str:
    """
    Build a human-readable error detail string for Slack.

    Surfaces information that the SDK's own exception messages hide:
    - The exception type name (so we can tell SDK errors from auth errors apart)
    - Chained __cause__ / __context__ when present
    - A diagnostic hint when stderr is empty AND the SDK message contains
      "Check stderr output for details" — that combination is the signature
      of an opaque CLI failure (auth, missing CLI binary, MCP startup) and
      always means "go run `claude --print` directly on the host".
    """
    parts: list[str] = []

    if stderr_output:
        parts.append(stderr_output.strip())
    else:
        parts.append(f"{type(exc).__name__}: {str(exc)}")
        if exc.__cause__ is not None:
            parts.append(f"caused by {type(exc.__cause__).__name__}: {exc.__cause__}")
        elif exc.__context__ is not None:
            parts.append(f"during handling of {type(exc.__context__).__name__}: {exc.__context__}")

    if exit_code is not None:
        parts.append(f"(exit code {exit_code})")

    parts.append(f"CWD: {cwd}")

    # Diagnostic hint for the opaque-CLI-failure pattern
    if not stderr_output and "Check stderr output for details" in str(exc):
        parts.append(
            "DIAGNOSTIC: stderr is empty and the SDK reports a CLI failure. "
            "This usually means the underlying `claude` CLI exited before our "
            "stderr callback could capture anything (auth failure, missing CLI, "
            "MCP server crash). Run on the host as the bot user to see the real "
            "error: `cd " + cwd + " && echo hi | claude --print "
            "--permission-mode=bypassPermissions 2>&1`"
        )

    return "\n".join(parts)


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

    stderr_lines: list[str] = []

    options = ClaudeAgentOptions(
        cwd=effective_cwd,
        resume=session_id,          # None for new session, str for resume
        max_turns=max_turns,
        permission_mode="bypassPermissions",
        mcp_servers=mcp_servers,
        add_dirs=add_dirs,
        stderr=lambda line: stderr_lines.append(line),
    )

    new_session_id = session_id
    result_text = None
    subtype = "unknown"
    num_turns = 0
    partial_texts = []

    try:
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
    except ProcessError as exc:
        stderr_output = "\n".join(stderr_lines[-20:])
        # If session resume failed, retry with a fresh session
        if session_id:
            log.warning(
                "agent.resume_failed_retrying",
                session_id=session_id,
                exit_code=exc.exit_code,
                cwd=effective_cwd,
            )
            return await run_agent(
                prompt, None, cwd=cwd,
                on_text=on_text, on_message=on_message, max_turns=max_turns,
            )
        log.error(
            "agent.process_error",
            session_id=session_id,
            exit_code=exc.exit_code,
            cwd=effective_cwd,
            stderr_preview=stderr_output[:1000],
        )
        error_detail = _format_error_detail(
            exc, stderr_output, effective_cwd, exit_code=exc.exit_code,
        )
        return {
            "session_id": session_id,
            "result": error_detail,
            "subtype": "error_internal",
            "num_turns": num_turns,
            "partial_texts": partial_texts,
        }
    except Exception as exc:
        # SDK sometimes raises generic Exception instead of ProcessError
        # (e.g. "Fatal error in message reader" at query.py:655)
        stderr_output = "\n".join(stderr_lines[-20:])
        if session_id:
            log.warning(
                "agent.generic_error_retrying",
                session_id=session_id,
                error=str(exc),
                error_type=type(exc).__name__,
                cwd=effective_cwd,
            )
            return await run_agent(
                prompt, None, cwd=cwd,
                on_text=on_text, on_message=on_message, max_turns=max_turns,
            )
        log.error(
            "agent.generic_error",
            session_id=session_id,
            error=str(exc),
            error_type=type(exc).__name__,
            error_repr=repr(exc),
            cause=repr(exc.__cause__) if exc.__cause__ else None,
            context=repr(exc.__context__) if exc.__context__ else None,
            cwd=effective_cwd,
            stderr_preview=stderr_output[:1000],
        )
        error_detail = _format_error_detail(
            exc, stderr_output, effective_cwd, exit_code=None,
        )
        return {
            "session_id": session_id,
            "result": error_detail,
            "subtype": "error_internal",
            "num_turns": num_turns,
            "partial_texts": partial_texts,
        }

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

    Captures partial_texts via a shared list so they survive timeout
    cancellation -- the user sees what the agent was last working on.

    Args:
        prompt: The user's prompt text.
        session_id: Session ID to resume, or None for a new session.
        cwd: Optional working directory override (e.g. worktree path).
        on_text: Optional async callback invoked with each AssistantMessage text.
        on_message: Optional async callback invoked with the full AssistantMessage.
        timeout_seconds: Wall-clock timeout in seconds (default 1800).
        max_turns: Maximum conversation turns (default 25).

    Returns:
        dict with keys: session_id, result, subtype, num_turns, partial_texts
    """
    # Shared mutable state so partial_texts survive timeout cancellation
    shared_partials: list[str] = []

    async def _capturing_on_text(text: str):
        shared_partials.append(text)
        if on_text:
            await on_text(text)

    try:
        return await asyncio.wait_for(
            run_agent(
                prompt,
                session_id,
                cwd=cwd,
                on_text=_capturing_on_text,
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
            partial_count=len(shared_partials),
        )
        return {
            "session_id": session_id,   # Retain prior session_id -- can still resume
            "result": None,
            "subtype": "error_timeout",
            "num_turns": -1,
            "partial_texts": shared_partials,
        }
