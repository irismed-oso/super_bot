"""
Pipeline status tool -- query Prefect flow runs and display grouped summary.

Shows flow runs grouped by status (failed first, then running, then completed)
with timestamps, run names, and durations. Callable as a CLI for agent use:

    python -m bot.pipeline_status              # last 24 hours
    python -m bot.pipeline_status --hours 48   # last 48 hours
    python -m bot.pipeline_status --since 2026-03-25  # since a specific date
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import httpx

from bot.prefect_api import PREFECT_API, PREFECT_AUTH

# State type groupings
_FAILED_STATES = {"FAILED", "CRASHED"}
_RUNNING_STATES = {"RUNNING", "PENDING", "SCHEDULED"}
_COMPLETED_STATES = {"COMPLETED"}
_OTHER_STATES = {"CANCELLING", "CANCELLED"}

MAX_COMPLETED_SHOWN = 10
MAX_OUTPUT_CHARS = 2500


async def fetch_flow_runs(
    hours: int | None = None,
    since: str | None = None,
) -> list[dict]:
    """Fetch flow runs from the Prefect API within a time window.

    Args:
        hours: Number of hours to look back (default 24).
        since: ISO date/datetime string to use as window start.

    Returns:
        List of flow run dicts from the Prefect API.
    """
    if since:
        try:
            # Try full datetime first, then date-only
            if "T" in since:
                window_start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
            else:
                window_start = datetime.fromisoformat(since).replace(
                    hour=0, minute=0, second=0, tzinfo=timezone.utc
                )
        except ValueError:
            print(f"Invalid date format: {since}. Use YYYY-MM-DD or ISO datetime.", file=sys.stderr)
            return []
    else:
        h = hours if hours else 24
        window_start = datetime.now(timezone.utc) - timedelta(hours=h)

    filter_body = {
        "flow_runs": {
            "start_time": {
                "after_": window_start.isoformat(),
            },
        },
        "sort": "START_TIME_DESC",
        "limit": 100,
    }

    try:
        async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=15) as client:
            resp = await client.post(
                f"{PREFECT_API}/flow_runs/filter",
                json=filter_body,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        print("Error: Cannot reach Prefect API. Is the server running?", file=sys.stderr)
        return []
    except httpx.HTTPStatusError as exc:
        print(f"Error: Prefect API returned {exc.response.status_code}.", file=sys.stderr)
        return []
    except Exception as exc:
        print(f"Error querying Prefect API: {exc}", file=sys.stderr)
        return []


def _get_state_type(run: dict) -> str:
    """Extract state type from a flow run dict."""
    state = run.get("state")
    if state and isinstance(state, dict):
        return state.get("type", "UNKNOWN")
    return "UNKNOWN"


def _get_state_message(run: dict) -> str:
    """Extract state message (error details) from a flow run dict."""
    state = run.get("state")
    if state and isinstance(state, dict):
        return state.get("message", "") or ""
    return ""


def _format_duration(run: dict) -> str:
    """Calculate and format run duration."""
    start = run.get("start_time")
    end = run.get("end_time")
    if not start:
        return ""
    try:
        st = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if end:
            et = datetime.fromisoformat(end.replace("Z", "+00:00"))
        else:
            et = datetime.now(timezone.utc)
        delta = et - st
        total_secs = int(delta.total_seconds())
        if total_secs < 60:
            return f"{total_secs}s"
        minutes = total_secs // 60
        secs = total_secs % 60
        if minutes < 60:
            return f"{minutes}m{secs}s"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h{mins}m"
    except (ValueError, TypeError):
        return ""


def _format_time(iso_str: str | None) -> str:
    """Format an ISO timestamp to a readable short form."""
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%m/%d %H:%M")
    except (ValueError, TypeError):
        return iso_str[:16] if iso_str else "N/A"


def _format_run_line(run: dict, show_error: bool = False) -> str:
    """Format a single flow run as a display line."""
    name = run.get("name", "unknown")
    start = _format_time(run.get("start_time"))
    duration = _format_duration(run)
    dur_part = f" ({duration})" if duration else ""

    line = f"  {name} | {start}{dur_part}"

    if show_error:
        msg = _get_state_message(run)
        if msg:
            # Truncate long error messages
            short_msg = msg[:120].replace("\n", " ").strip()
            if len(msg) > 120:
                short_msg += "..."
            line += f"\n    {short_msg}"

    return line


def format_pipeline_summary(runs: list[dict], window_label: str = "last 24h") -> str:
    """Format flow runs into a grouped summary string.

    Args:
        runs: List of flow run dicts from the Prefect API.
        window_label: Human-readable time window description.

    Returns:
        Formatted summary string, kept under MAX_OUTPUT_CHARS.
    """
    if not runs:
        return "No flow runs found in the specified time window."

    # Group by state
    failed = []
    running = []
    completed = []
    other = []

    for run in runs:
        st = _get_state_type(run)
        if st in _FAILED_STATES:
            failed.append(run)
        elif st in _RUNNING_STATES:
            running.append(run)
        elif st in _COMPLETED_STATES:
            completed.append(run)
        else:
            other.append(run)

    # Build summary line
    parts = []
    parts.append(f"{len(completed)} completed")
    if failed:
        parts.append(f"{len(failed)} failed")
    if running:
        parts.append(f"{len(running)} running")
    if other:
        parts.append(f"{len(other)} other")

    lines = [f"Pipeline Status ({window_label}): {', '.join(parts)}"]
    lines.append("")

    # Failed section (always shown first, with emphasis)
    if failed:
        lines.append(f"FAILED ({len(failed)}):")
        for run in failed:
            lines.append(_format_run_line(run, show_error=True))
        lines.append("")

    # Running section
    if running:
        lines.append(f"Running ({len(running)}):")
        for run in running:
            lines.append(_format_run_line(run))
        lines.append("")

    # Completed section (capped)
    if completed:
        shown = completed[:MAX_COMPLETED_SHOWN]
        lines.append(f"Completed ({len(completed)}):")
        for run in shown:
            lines.append(_format_run_line(run))
        remaining = len(completed) - len(shown)
        if remaining > 0:
            lines.append(f"  ... and {remaining} more completed")
        lines.append("")

    # Other section
    if other:
        lines.append(f"Other ({len(other)}):")
        for run in other:
            lines.append(_format_run_line(run))
        lines.append("")

    output = "\n".join(lines).rstrip()

    # Truncate if needed (trim completed section)
    if len(output) > MAX_OUTPUT_CHARS:
        # Rebuild with fewer completed runs
        trimmed_count = max(3, MAX_COMPLETED_SHOWN // 2)
        lines_trimmed = [f"Pipeline Status ({window_label}): {', '.join(parts)}"]
        lines_trimmed.append("")

        if failed:
            lines_trimmed.append(f"FAILED ({len(failed)}):")
            for run in failed:
                lines_trimmed.append(_format_run_line(run, show_error=True))
            lines_trimmed.append("")

        if running:
            lines_trimmed.append(f"Running ({len(running)}):")
            for run in running:
                lines_trimmed.append(_format_run_line(run))
            lines_trimmed.append("")

        if completed:
            shown = completed[:trimmed_count]
            lines_trimmed.append(f"Completed ({len(completed)}):")
            for run in shown:
                lines_trimmed.append(_format_run_line(run))
            remaining = len(completed) - len(shown)
            if remaining > 0:
                lines_trimmed.append(f"  ... and {remaining} more completed")
            lines_trimmed.append("")

        output = "\n".join(lines_trimmed).rstrip()

    return output


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bot.pipeline_status",
        description="Show Prefect pipeline status -- flow runs grouped by state.",
    )
    parser.add_argument(
        "--hours", type=int, default=None,
        help="Look back N hours (default: 24)",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Start time as ISO date (YYYY-MM-DD) or datetime",
    )
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if args.since and args.hours:
        print("Use either --hours or --since, not both.", file=sys.stderr)
        sys.exit(1)

    # Build window label
    if args.since:
        window_label = f"since {args.since}"
    elif args.hours:
        window_label = f"last {args.hours}h"
    else:
        window_label = "last 24h"

    runs = asyncio.run(fetch_flow_runs(hours=args.hours, since=args.since))
    summary = format_pipeline_summary(runs, window_label=window_label)
    print(summary)


if __name__ == "__main__":
    main()
