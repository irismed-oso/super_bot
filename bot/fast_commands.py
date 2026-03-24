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
from datetime import date

import structlog

from bot import prefect_api

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
# Location aliases — canonical names for all 23 EyeMed locations
# ---------------------------------------------------------------------------

LOCATION_ALIASES = {
    # Single-word locations (lowercase key -> canonical name)
    "boomtown": "Boomtown",
    "brenham": "Brenham",
    "clasik": "Clasik",
    "coastal": "Coastal",
    "dme": "DME",
    "eclant": "ECLANT",
    "ecec": "ECEC",
    "elite": "Elite",
    "emec": "EMEC",
    "feg": "FEG",
    "insights": "Insights",
    "lonestar": "LONESTAR",
    "msoc": "MSOC",
    "oec": "OEC",
    "optique": "OPTIQUE",
    "peg": "PEG",
    "premier": "Premier",
    "pvec": "PVEC",
    "tsoh": "TSOH",
    "tsos": "TSOS",
    "wagner": "Wagner",
    "westlake": "Westlake",
    # Multi-word locations (both hyphenated and space-separated)
    "optical image": "Optical Image",
    "optical-image": "Optical Image",
}

# Sorted by length descending so "optical image" matches before "optical"
_alias_keys_sorted = sorted(LOCATION_ALIASES.keys(), key=len, reverse=True)

# Dynamic regex that matches any known location name in the text
_LOCATION_EXTRACT_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _alias_keys_sorted) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# EyeMed crawl
# ---------------------------------------------------------------------------

_EYEMED_CRAWL_RE = re.compile(
    r"crawl\s+(?:eyemed\s+)?(\S+)(?:\s+(.+))?",
    re.IGNORECASE,
)


async def _handle_eyemed_crawl(text: str) -> str:
    """Trigger a Prefect EyeMed crawl deployment for a single location."""
    m = _EYEMED_CRAWL_RE.search(text)
    if not m:
        return "Could not parse crawl command."

    raw_location = m.group(1).strip()
    date_part = m.group(2).strip() if m.group(2) else None

    # Resolve location alias (case-insensitive)
    canonical = LOCATION_ALIASES.get(raw_location.lower())
    if not canonical:
        valid = ", ".join(sorted(set(LOCATION_ALIASES.values())))
        return f"Unknown location '{raw_location}'. Known locations: {valid}"

    # Parse date from the capture group or full text
    date_str = None
    if date_part:
        date_match = _DATE_RE.search(date_part)
        if date_match:
            date_str = date_match.group(1).replace("/", ".")
    if not date_str:
        date_match = _DATE_RE.search(text)
        if date_match:
            date_str = date_match.group(1).replace("/", ".")

    if not date_str:
        return "Please specify a date, e.g., 'crawl eyemed DME 03.20.26'"

    # Normalize date to MM.DD.YY
    date_str = _normalize_date(date_str)

    # Build deployment name (matches eyemed_crawler_deployments.py convention)
    deployment_name = f"eyemed-crawler-{canonical.lower().replace(' ', '-')}-manual"

    dep_id = await prefect_api.find_deployment_id(deployment_name)
    if not dep_id:
        return (
            f"Deployment '{deployment_name}' not found in Prefect. "
            "Check that the deployment exists and is active."
        )

    parameters = {
        "location": canonical,
        "headless": True,
        "skip_s3": False,
        "skip_gcs": False,
        "skip_gdrive": False,
        "days_back": 1,
        "date_from": date_str,
        "date_to": date_str,
    }

    result = await prefect_api.create_flow_run(dep_id, parameters)
    flow_run_id = result.get("id", "unknown")
    flow_run_name = result.get("name", "unknown")

    return (
        f"Triggered EyeMed crawl for {canonical} ({date_str})\n"
        f"Deployment: `{deployment_name}`\n"
        f"Flow run: `{flow_run_name}` ({flow_run_id[:8]})"
    )


# ---------------------------------------------------------------------------
# EyeMed status
# ---------------------------------------------------------------------------

_EYEMED_STATUS_RE = re.compile(
    r"eyemed\s+(?:scan\s+)?status"
    r"|status.*eyemed"
    r"|status\s+on\s+\S+\s+eyemed"
    r"|eyemed.*(?:today|yesterday|status|report|audit)",
    re.IGNORECASE,
)

# Extract date-like arguments: MM.DD.YY, MM/DD/YY, "last N days", "past N days"
_DATE_RE = re.compile(r"\b(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)\b")
_DAYS_BACK_RE = re.compile(r"(?:last|past)\s+(\d+)\s+days?", re.IGNORECASE)
_LOCATION_RE = re.compile(
    r"\b(?:for|at|location)\s+([A-Za-z][\w\s]*?)(?:\s*(?:today|yesterday|status|$))",
    re.IGNORECASE,
)


def _normalize_date(d: str) -> str:
    """Normalize a date string to MM.DD.YY format, appending current year if missing."""
    parts = re.split(r"[./]", d)
    if len(parts) == 2:
        # MM.DD -> append current 2-digit year
        yy = str(date.today().year % 100).zfill(2)
        return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}.{yy}"
    elif len(parts) == 3:
        year_part = parts[2]
        if len(year_part) == 4:
            year_part = year_part[-2:]
        return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}.{year_part}"
    return d


def _today_mmddyy() -> str:
    """Return today's date as MM.DD.YY."""
    t = date.today()
    return f"{t.month:02d}.{t.day:02d}.{t.year % 100:02d}"


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
        d1 = _normalize_date(dates[0].replace("/", "."))
        d2 = _normalize_date(dates[1].replace("/", "."))
        args.extend(["--from", d1, "--to", d2])
    elif len(dates) == 1:
        d = _normalize_date(dates[0].replace("/", "."))
        args.extend(["--from", d])
        # Check for "to today" / "to now"
        if re.search(r"\bto\s+(?:today|now)\b", text, re.IGNORECASE):
            args.extend(["--to", _today_mmddyy()])
        else:
            args.extend(["--to", d])

    # Handle "today" / "to today" when no explicit dates at all
    if not dates and "today" in text.lower() and not days_match:
        today = _today_mmddyy()
        args.extend(["--from", today, "--to", today])

    # Parse location: try smart extraction first, then fall back to old regex
    loc_match = _LOCATION_EXTRACT_RE.search(text)
    if loc_match:
        canonical = LOCATION_ALIASES.get(loc_match.group(1).lower())
        if canonical:
            args.extend(["--location", canonical])
    else:
        loc_match_old = _LOCATION_RE.search(text)
        if loc_match_old:
            args.extend(["--location", loc_match_old.group(1).strip()])

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
# NOTE: Crawl MUST come before status -- "crawl eyemed DME" would otherwise
# match the status regex's "status.*eyemed" alternation.
FAST_COMMANDS = [
    (_EYEMED_CRAWL_RE, _handle_eyemed_crawl),
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
