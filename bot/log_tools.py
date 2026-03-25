"""
Log access tools for journald and Prefect flow run logs.

Provides structured parsing of structlog JSON, secret scrubbing,
and Slack-safe truncation. Callable as a CLI for agent pipeline use:

    python -m bot.log_tools journald superbot --lines 50 --grep error --since "1h"
    python -m bot.log_tools prefect <run-id-or-name>
"""

import argparse
import asyncio
import json
import re
import sys

import httpx
import structlog

from bot.deploy_state import REPO_CONFIG
from bot.prefect_api import PREFECT_API, PREFECT_AUTH

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Service alias resolution
# ---------------------------------------------------------------------------

# Additional aliases beyond what REPO_CONFIG provides
_EXTRA_ALIASES = {
    "sb": "super_bot",
    "mt": "mic_transformer",
}


def resolve_service_name(alias: str) -> str | None:
    """Resolve a user-facing alias to a systemd unit name.

    Uses REPO_CONFIG from deploy_state.py. Returns None if not recognized.
    """
    lower = alias.lower().strip()

    # Check REPO_CONFIG aliases and canonical names
    for name, cfg in REPO_CONFIG.items():
        if lower == name or lower in cfg.get("aliases", []):
            service = cfg.get("service")
            # If service is None, fall back to canonical name
            return service if service else name

    # Check extra aliases
    if lower in _EXTRA_ALIASES:
        canonical = _EXTRA_ALIASES[lower]
        cfg = REPO_CONFIG.get(canonical, {})
        service = cfg.get("service")
        return service if service else canonical

    return None


# ---------------------------------------------------------------------------
# Structlog parsing
# ---------------------------------------------------------------------------


def parse_structlog_line(line: str) -> str:
    """Parse a single log line, handling both structlog JSON and plain text.

    For JSON lines with timestamp/level/event keys, returns a readable format.
    For plain text, returns as-is.
    """
    stripped = line.strip()
    if not stripped:
        return stripped

    if not stripped.startswith("{"):
        return stripped

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return stripped

    # Check for structlog-style keys
    timestamp = data.get("timestamp", "")
    level = data.get("level", "")
    event = data.get("event", "")

    if not event:
        return stripped

    # Build readable line
    parts = []
    if timestamp:
        parts.append(str(timestamp))
    if level:
        parts.append(level.upper())
    parts.append(str(event))

    # Append useful extra keys
    skip_keys = {"timestamp", "level", "event", "logger", "module", "lineno"}
    extras = []
    for k, v in data.items():
        if k not in skip_keys and v is not None and v != "":
            extras.append(f"{k}={v}")
    if extras:
        parts.append(" ".join(extras))

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Secret scrubbing
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    # Slack tokens
    (re.compile(r"xox[bprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED]"),
    # API keys starting with sk-
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED]"),
    # AWS access key IDs
    (re.compile(r"AKIA[A-Z0-9]{16}"), "[REDACTED]"),
    # Bearer tokens
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.~+/]{20,}"), "Bearer [REDACTED]"),
    # Passwords in URLs (user:pass@host)
    (re.compile(r"://[^:]+:([^@]{3,})@"), "://[user]:[REDACTED]@"),
    # Generic API key patterns in key=value
    (re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*\S{8,}"),
     lambda m: f"{m.group(1)}=[REDACTED]"),
]


def scrub_secrets(text: str) -> str:
    """Remove common secret patterns from text.

    Conservative approach -- better to miss a secret than mangle real data.
    """
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        if callable(replacement):
            result = pattern.sub(replacement, result)
        else:
            result = pattern.sub(replacement, result)
    return result


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_log_output(raw_text: str, max_chars: int = 2800) -> str:
    """Parse, scrub, and truncate log output for Slack.

    Parses each line through structlog parser, scrubs secrets,
    and truncates from the beginning (keeping most recent lines)
    if output exceeds max_chars.
    """
    lines = raw_text.splitlines()
    parsed = [parse_structlog_line(line) for line in lines]
    total_lines = len(parsed)

    # Join and scrub
    output = "\n".join(parsed)
    output = scrub_secrets(output)

    if len(output) <= max_chars:
        return output

    # Truncate from the beginning, keeping recent lines
    kept = []
    char_count = 0
    for line in reversed(parsed):
        scrubbed_line = scrub_secrets(line)
        if char_count + len(scrubbed_line) + 1 > max_chars - 60:  # reserve space for header
            break
        kept.append(scrubbed_line)
        char_count += len(scrubbed_line) + 1  # +1 for newline

    kept.reverse()
    header = f"... (showing last {len(kept)} of {total_lines} lines)"
    return header + "\n" + "\n".join(kept)


# ---------------------------------------------------------------------------
# Journald log retrieval
# ---------------------------------------------------------------------------


async def fetch_journald_logs(
    service: str,
    lines: int = 100,
    grep: str | None = None,
    since: str | None = None,
) -> str:
    """Fetch journald logs for a systemd service.

    Args:
        service: Service alias (e.g. "superbot", "mic").
        lines: Number of lines to retrieve.
        grep: Optional grep pattern (case-insensitive).
        since: Optional time spec (e.g. "1h", "30m", "2h").

    Returns:
        Formatted, truncated, scrubbed log output.
    """
    unit = resolve_service_name(service)
    if not unit:
        return f"Unknown service: {service}. Available: {', '.join(_all_aliases())}"

    cmd = ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "--output=short-iso"]

    if grep:
        cmd.extend(["--grep", grep, "--case-sensitive=no"])

    if since:
        # Normalize: "1h" -> "1 hour ago", "30m" -> "30 minutes ago"
        time_spec = _normalize_since(since)
        cmd.extend(["--since", time_spec])

    log.info("log_tools.journald", unit=unit, cmd=" ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode().strip()
            if "No entries" in err or not stdout:
                return f"No log entries found for {unit}."
            return f"journalctl error: {err[:500]}"

        raw = stdout.decode()
        if not raw.strip():
            return f"No log entries found for {unit}."

        return format_log_output(raw)

    except FileNotFoundError:
        return "journalctl not found -- are you running on the VM?"
    except Exception as exc:
        log.error("log_tools.journald_error", error=str(exc))
        return f"Error fetching logs: {exc}"


def _normalize_since(spec: str) -> str:
    """Normalize shorthand time specs to journalctl --since format.

    "1h" -> "1 hour ago"
    "30m" -> "30 minutes ago"
    "2d" -> "2 days ago"
    Already-valid specs pass through.
    """
    spec = spec.strip()
    match = re.match(r"^(\d+)\s*([hHmMdDsS])$", spec)
    if match:
        num = match.group(1)
        unit = match.group(2).lower()
        units = {"h": "hour", "m": "minute", "d": "day", "s": "second"}
        word = units.get(unit, unit)
        if int(num) != 1:
            word += "s"
        return f"{num} {word} ago"
    # Pass through specs that already look complete
    return spec


def _all_aliases() -> list[str]:
    """Return all recognized service aliases."""
    aliases = []
    for cfg in REPO_CONFIG.values():
        aliases.extend(cfg.get("aliases", []))
    return aliases


# ---------------------------------------------------------------------------
# Prefect log retrieval
# ---------------------------------------------------------------------------


async def fetch_prefect_logs(run_id_or_name: str) -> str:
    """Fetch logs for a Prefect flow run by ID or name.

    Args:
        run_id_or_name: Flow run UUID or flow run name (e.g. "turquoise-fox").

    Returns:
        Formatted, truncated log output.
    """
    try:
        async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=15) as client:
            # Try as UUID first
            flow_run_id = run_id_or_name
            if not _is_uuid(run_id_or_name):
                # Search by name
                flow_run_id = await _find_flow_run_by_name(client, run_id_or_name)
                if not flow_run_id:
                    return f"No flow run found matching: {run_id_or_name}"

            # Fetch logs
            resp = await client.post(
                f"{PREFECT_API}/flow_runs/{flow_run_id}/logs",
                json={"sort": "TIMESTAMP_ASC", "limit": 200},
            )
            resp.raise_for_status()
            data = resp.json()

            logs = data if isinstance(data, list) else data.get("logs", [])
            if not logs:
                return f"No logs found for flow run {run_id_or_name}."

            # Format log entries
            lines = []
            for entry in logs:
                ts = entry.get("timestamp", "")
                level = entry.get("level", 0)
                level_name = _prefect_level_name(level)
                message = entry.get("message", "")
                lines.append(f"{ts} {level_name} {message}")

            raw = "\n".join(lines)
            return format_log_output(raw)

    except Exception as exc:
        log.error("log_tools.prefect_error", error=str(exc))
        return f"Error fetching Prefect logs: {exc}"


async def _find_flow_run_by_name(client: httpx.AsyncClient, name: str) -> str | None:
    """Find a flow run ID by its name."""
    resp = await client.post(
        f"{PREFECT_API}/flow_runs/filter",
        json={
            "flow_runs": {"name": {"any_": [name]}},
            "sort": "START_TIME_DESC",
            "limit": 1,
        },
    )
    resp.raise_for_status()
    results = resp.json()
    if results:
        return results[0]["id"]
    return None


def _is_uuid(text: str) -> bool:
    """Check if text looks like a UUID."""
    return bool(re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        text.lower(),
    ))


def _prefect_level_name(level: int) -> str:
    """Convert Prefect numeric log level to name."""
    if level >= 40:
        return "ERROR"
    if level >= 30:
        return "WARNING"
    if level >= 20:
        return "INFO"
    if level >= 10:
        return "DEBUG"
    return "TRACE"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bot.log_tools",
        description="Fetch and format service logs for Slack display.",
    )
    sub = parser.add_subparsers(dest="command", help="Log source")

    # journald subcommand
    j = sub.add_parser("journald", help="Fetch journald service logs")
    j.add_argument("service", help="Service name or alias (e.g. superbot, mic)")
    j.add_argument("--lines", "-n", type=int, default=50, help="Number of lines (default: 50)")
    j.add_argument("--grep", "-g", help="Filter pattern (case-insensitive)")
    j.add_argument("--since", "-s", help="Time range (e.g. 1h, 30m, 2d)")

    # prefect subcommand
    p = sub.add_parser("prefect", help="Fetch Prefect flow run logs")
    p.add_argument("run_id", help="Flow run ID (UUID) or name (e.g. turquoise-fox)")

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "journald":
        result = asyncio.run(fetch_journald_logs(
            service=args.service,
            lines=args.lines,
            grep=args.grep,
            since=args.since,
        ))
    elif args.command == "prefect":
        result = asyncio.run(fetch_prefect_logs(args.run_id))
    else:
        parser.print_help()
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
