"""
Post-session git activity capture for the daily changelog.

After each agent session completes, parses git log output to find new
commits and extracts PR/MR URLs from the result text. All entries are
appended to the JSONL activity log for Phase 10 (Digest Changelog).
"""

import asyncio
from datetime import date, datetime, timezone

import structlog

from bot import activity_log
from bot.progress import PR_URL_RE

log = structlog.get_logger(__name__)


async def capture_git_activity(
    result: dict,
    cwd: str | None,
    channel: str,
    thread_ts: str,
) -> list[dict]:
    """Capture git commits and PRs produced during an agent session.

    Runs after the agent completes. Parses git log for new commits in the
    worktree and scans result text for PR/MR URLs. Appends structured
    entries to the activity log.

    Returns the list of entries appended (for logging/testing).
    """
    entries: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    # Capture commits from worktree
    if cwd is not None:
        try:
            commit_entries = await _capture_commits(cwd, channel, thread_ts, now)
            entries.extend(commit_entries)
        except Exception as exc:
            log.warning("git_activity.commit_capture_failed", error=str(exc), cwd=cwd)

    # Capture PR URLs from result text
    try:
        pr_entries = _capture_prs(result, channel, thread_ts, now)
        entries.extend(pr_entries)
    except Exception as exc:
        log.warning("git_activity.pr_capture_failed", error=str(exc))

    return entries


async def _capture_commits(
    cwd: str, channel: str, thread_ts: str, now: str,
) -> list[dict]:
    """Parse git log in the worktree for commits not yet on origin/develop."""
    # Get repo name via git rev-parse --show-toplevel
    repo = await _get_repo_name(cwd)
    branch = await _get_branch_name(cwd)

    # Get commits: try origin/develop..HEAD first, fall back to HEAD~10..HEAD
    log_output = await _run_git_log(cwd, "origin/develop..HEAD")
    if log_output is None:
        log_output = await _run_git_log(cwd, "HEAD~10..HEAD")
    if not log_output:
        return []

    # Parse commits
    commits = _parse_git_log(log_output, repo, branch)
    if not commits:
        return []

    # Deduplicate against already-logged commits for this thread today
    existing = activity_log.read_day(date.today())
    logged_hashes = {
        e.get("hash")
        for e in existing
        if e.get("type") == "git_commit" and e.get("thread_ts") == thread_ts
    }

    entries = []
    for commit in commits:
        if commit["hash"] in logged_hashes:
            continue
        entry = {
            "type": "git_commit",
            "hash": commit["hash"],
            "message": commit["message"],
            "repo": commit["repo"],
            "branch": commit["branch"],
            "files": commit["files"],
            "channel": channel,
            "thread_ts": thread_ts,
            "ts": now,
        }
        activity_log.append(entry)
        entries.append(entry)

    return entries


async def _get_repo_name(cwd: str) -> str:
    """Get repo name from git rev-parse --show-toplevel, taking basename."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--show-toplevel",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0 and stdout:
            import os
            return os.path.basename(stdout.decode().strip())
    except Exception:
        pass
    # Fallback: use cwd basename
    import os
    return os.path.basename(cwd)


async def _get_branch_name(cwd: str) -> str:
    """Get current branch name."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--abbrev-ref", "HEAD",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0 and stdout:
            return stdout.decode().strip()
    except Exception:
        pass
    return "unknown"


async def _run_git_log(cwd: str, rev_range: str) -> str | None:
    """Run git log with --format and --name-only. Returns stdout or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", f"--format=%H|%s", "--name-only", rev_range,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode()
    except Exception:
        pass
    return None


def _parse_git_log(output: str, repo: str, branch: str) -> list[dict]:
    """Parse git log --format='%H|%s' --name-only output into commit dicts."""
    commits = []
    current_commit = None
    current_files = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            # Blank line separates commit header from file list
            continue
        if "|" in line and len(line.split("|", 1)[0]) == 40:
            # This looks like a commit header: full_sha|subject
            if current_commit is not None:
                current_commit["files"] = current_files
                commits.append(current_commit)
            parts = line.split("|", 1)
            current_commit = {
                "hash": parts[0],
                "message": parts[1] if len(parts) > 1 else "",
                "repo": repo,
                "branch": branch,
            }
            current_files = []
        elif current_commit is not None:
            # File path line
            current_files.append(line)

    # Don't forget the last commit
    if current_commit is not None:
        current_commit["files"] = current_files
        commits.append(current_commit)

    return commits


def _capture_prs(
    result: dict, channel: str, thread_ts: str, now: str,
) -> list[dict]:
    """Extract PR/MR URLs from the agent result text."""
    result_text = result.get("result", "") or ""
    urls = PR_URL_RE.findall(result_text)
    if not urls:
        return []

    entries = []
    for url in urls:
        title = _extract_pr_title(url, result_text)
        repo = _repo_from_url(url)
        entry = {
            "type": "git_pr",
            "url": url,
            "title": title,
            "repo": repo,
            "channel": channel,
            "thread_ts": thread_ts,
            "ts": now,
        }
        activity_log.append(entry)
        entries.append(entry)

    return entries


def _extract_pr_title(url: str, result_text: str) -> str:
    """Try to extract a PR title from the result text near the URL."""
    for text_line in result_text.splitlines():
        if url in text_line:
            # Remove the URL itself and clean up
            remainder = text_line.replace(url, "").strip()
            # Strip common prefixes/suffixes
            for prefix in ("PR:", "MR:", "-", "*", "Created", "Opened"):
                remainder = remainder.lstrip(prefix).strip()
            if remainder and len(remainder) > 3:
                return remainder[:200]
    # Fallback: extract from URL path
    if "/pull/" in url:
        return "pull/" + url.split("/pull/")[-1]
    if "/merge_requests/" in url:
        return "merge_requests/" + url.split("/merge_requests/")[-1]
    return url.split("/")[-1]


def _repo_from_url(url: str) -> str:
    """Extract repo name from a GitHub/GitLab PR URL."""
    # github.com/org/repo/pull/42 -> repo
    # gitlab.com/org/repo/-/merge_requests/42 -> repo
    parts = url.replace("https://", "").split("/")
    # parts: [domain, org, repo, ...]
    if len(parts) >= 3:
        return parts[2]
    return "unknown"
