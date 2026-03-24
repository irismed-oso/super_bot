"""
Fast-path handlers for common queries that don't need the full agent pipeline.

Pattern-match incoming messages and run scripts/queries directly, returning
formatted Slack responses in seconds instead of minutes.

Add new fast commands by adding entries to FAST_COMMANDS with a regex pattern
and an async handler function.
"""

import asyncio
import os
import re

import structlog

log = structlog.get_logger(__name__)

MIC_TRANSFORMER_DIR = os.path.realpath(
    os.environ.get("MIC_TRANSFORMER_CWD", "/home/bot/mic_transformer")
)
MIC_TRANSFORMER_PYTHON = os.path.join(MIC_TRANSFORMER_DIR, ".venv", "bin", "python")

# Timeout for fast command subprocess execution (seconds)
FAST_CMD_TIMEOUT = 30


async def _run_script(script_path: str, args: list[str], cwd: str = None) -> str:
    """Run a Python script and return its stdout. Raises on failure."""
    cmd = [MIC_TRANSFORMER_PYTHON, script_path] + args
    effective_cwd = cwd or MIC_TRANSFORMER_DIR

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=effective_cwd,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=FAST_CMD_TIMEOUT
    )

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"Script failed (exit {proc.returncode}): {err[:500]}")

    return stdout.decode().strip()


# ---------------------------------------------------------------------------
# EyeMed status
# ---------------------------------------------------------------------------

_EYEMED_STATUS_RE = re.compile(
    r"eyemed\s+(?:scan\s+)?status"
    r"|status.*eyemed"
    r"|eyemed.*(?:today|yesterday|status|report|audit)",
    re.IGNORECASE,
)

# Extract date-like arguments: MM.DD.YY, MM/DD/YY, "last N days", "past N days"
_DATE_RE = re.compile(r"\b(\d{1,2}[./]\d{1,2}[./]\d{2,4})\b")
_DAYS_BACK_RE = re.compile(r"(?:last|past)\s+(\d+)\s+days?", re.IGNORECASE)
_LOCATION_RE = re.compile(
    r"\b(?:for|at|location)\s+([A-Za-z][\w\s]*?)(?:\s*(?:today|yesterday|status|$))",
    re.IGNORECASE,
)


async def _handle_eyemed_status(text: str) -> str:
    """Run the eyemed_scan_status.py script with args parsed from the message."""
    script = os.path.join(MIC_TRANSFORMER_DIR, "scripts", "eyemed_scan_status.py")
    if not os.path.isfile(script):
        raise FileNotFoundError(
            f"eyemed_scan_status.py not found at {script}. "
            "Has it been deployed to the VM?"
        )

    args = []

    # Parse days back
    days_match = _DAYS_BACK_RE.search(text)
    if days_match:
        args.extend(["--days", days_match.group(1)])

    # Parse explicit dates
    dates = _DATE_RE.findall(text)
    if len(dates) >= 2:
        # Normalize separators to dots
        d1 = dates[0].replace("/", ".")
        d2 = dates[1].replace("/", ".")
        args.extend(["--from", d1, "--to", d2])
    elif len(dates) == 1:
        d = dates[0].replace("/", ".")
        args.extend(["--from", d, "--to", d])

    # Parse location
    loc_match = _LOCATION_RE.search(text)
    if loc_match:
        args.extend(["--location", loc_match.group(1).strip()])

    # Check for "yesterday"
    if "yesterday" in text.lower() and not dates:
        args.extend(["--days", "1"])

    output = await _run_script(script, args)
    return output


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, async_handler_function)
# Handler receives the cleaned message text, returns formatted string.
FAST_COMMANDS = [
    (_EYEMED_STATUS_RE, _handle_eyemed_status),
]


async def try_fast_command(text: str) -> str | None:
    """
    Check if text matches a fast command pattern.

    Returns the formatted response string if matched, or None if no match
    (caller should fall through to the full agent pipeline).
    """
    for pattern, handler in FAST_COMMANDS:
        if pattern.search(text):
            try:
                log.info("fast_command.matched", pattern=pattern.pattern, text=text[:80])
                result = await handler(text)
                log.info("fast_command.success", pattern=pattern.pattern)
                return result
            except Exception as exc:
                log.error(
                    "fast_command.failed",
                    pattern=pattern.pattern,
                    error=str(exc),
                )
                # Fall through to agent on failure
                return None
    return None
