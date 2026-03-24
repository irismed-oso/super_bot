"""
Changelog section builder for the daily digest.

Queries the activity log for git commits and PRs, cross-checks against
git log output to catch any missed activity, groups entries by repository,
and formats a Slack-ready changelog block.
"""

import asyncio
import os
from datetime import date, timedelta

import structlog

import config
from bot import activity_log

log = structlog.get_logger(__name__)

# Maximum commits to show per repo before truncating
MAX_COMMITS_PER_REPO = 15


async def build_changelog_section(target_date: date) -> str:
    """Build a Slack-formatted changelog section for the given date.

    Queries the activity log for git_commit and git_pr entries, then
    cross-checks git log across all configured repos to catch commits
    missed by session logging (e.g., due to crashes).

    Returns an empty string if no git activity occurred.
    """
    # 1. Query activity log for logged entries
    logged_commits = activity_log.read_day_by_type(target_date, "git_commit")
    logged_prs = activity_log.read_day_by_type(target_date, "git_pr")

    # 2. Cross-check git log for missed commits
    missed_commits = await _cross_check_git_log(target_date, logged_commits)

    # 3. Group by repository
    by_repo = _group_by_repo(logged_commits + missed_commits, logged_prs)

    # 4. Format
    if not by_repo:
        return ""

    return _format_changelog(by_repo)


async def _cross_check_git_log(
    target_date: date, logged_commits: list[dict],
) -> list[dict]:
    """Scan all configured repos via git log to find commits not in the activity log."""
    logged_hashes = {e.get("hash", "") for e in logged_commits}

    # Build list of repo paths to scan
    repo_paths = []
    mic_cwd = os.environ.get("MIC_TRANSFORMER_CWD", "/home/bot/mic_transformer")
    repo_paths.append(mic_cwd)
    repo_paths.extend(config.ADDITIONAL_REPOS)

    missed: list[dict] = []
    since = f"{target_date.isoformat()}T00:00:00"
    until = f"{(target_date + timedelta(days=1)).isoformat()}T00:00:00"

    for repo_path in repo_paths:
        if not os.path.isdir(repo_path):
            continue
        try:
            entries = await _git_log_for_date(repo_path, since, until)
            repo_name = os.path.basename(repo_path)
            for entry in entries:
                if entry["hash"] not in logged_hashes:
                    entry["repo"] = repo_name
                    entry["recovered"] = True
                    missed.append(entry)
                    logged_hashes.add(entry["hash"])
        except Exception as exc:
            log.warning(
                "digest_changelog.crosscheck_failed",
                repo=repo_path,
                error=str(exc),
            )

    if missed:
        log.info("digest_changelog.missed_commits_found", count=len(missed))

    return missed


async def _resolve_bot_author(repo_path: str) -> str:
    """Get the bot's git author name from the repo config."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "config", "user.name",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0 and stdout.strip():
            return stdout.decode().strip()
    except Exception:
        pass
    return os.getlogin()


async def _git_log_for_date(
    repo_path: str, since: str, until: str,
) -> list[dict]:
    """Run git log for a date range, filtered to bot's commits only."""
    author_name = await _resolve_bot_author(repo_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", "--all",
            f"--author={author_name}",
            f"--since={since}", f"--until={until}",
            "--format=%H|%s", "--name-only",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            log.warning(
                "digest_changelog.git_log_failed",
                repo=repo_path,
                stderr=stderr.decode()[:200],
            )
            return []
        return _parse_git_log(stdout.decode())
    except Exception as exc:
        log.warning(
            "digest_changelog.git_subprocess_error",
            repo=repo_path,
            error=str(exc),
        )
        return []


def _parse_git_log(output: str) -> list[dict]:
    """Parse git log --format='%H|%s' --name-only output into commit dicts."""
    commits = []
    current_commit = None
    current_files: list[str] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line and len(line.split("|", 1)[0]) == 40:
            # Commit header: full_sha|subject
            if current_commit is not None:
                current_commit["files"] = current_files
                commits.append(current_commit)
            parts = line.split("|", 1)
            current_commit = {
                "hash": parts[0],
                "message": parts[1] if len(parts) > 1 else "",
            }
            current_files = []
        elif current_commit is not None:
            current_files.append(line)

    if current_commit is not None:
        current_commit["files"] = current_files
        commits.append(current_commit)

    return commits


def _group_by_repo(
    commits: list[dict], prs: list[dict],
) -> dict[str, dict]:
    """Group commits and PRs by repository name, sorted alphabetically."""
    by_repo: dict[str, dict] = {}

    for commit in commits:
        repo = commit.get("repo", "unknown")
        if repo not in by_repo:
            by_repo[repo] = {"commits": [], "prs": []}
        by_repo[repo]["commits"].append(commit)

    for pr in prs:
        repo = pr.get("repo", "unknown")
        if repo not in by_repo:
            by_repo[repo] = {"commits": [], "prs": []}
        by_repo[repo]["prs"].append(pr)

    # Return sorted by repo name
    return dict(sorted(by_repo.items()))


def _format_changelog(by_repo: dict[str, dict]) -> str:
    """Format grouped changelog entries into a Slack-ready block."""
    single_repo = len(by_repo) == 1

    # Build heading — include counts inline for single-repo case
    if single_repo:
        repo_name, data = next(iter(by_repo.items()))
        total_commits = len(data["commits"])
        total_prs = len(data["prs"])
        parts = []
        if total_commits:
            parts.append(f"{total_commits} commit{'s' if total_commits != 1 else ''}")
        if total_prs:
            parts.append(f"{total_prs} PR{'s' if total_prs != 1 else ''}")
        lines = [f"*Changelog* ({', '.join(parts)})", ""]
    else:
        lines = ["*Changelog*", ""]

    for repo_name, data in by_repo.items():
        commits = data["commits"]
        prs = data["prs"]

        # Show repo header only when multiple repos
        if not single_repo:
            parts = []
            if commits:
                parts.append(f"{len(commits)} commit{'s' if len(commits) != 1 else ''}")
            if prs:
                parts.append(f"{len(prs)} PR{'s' if len(prs) != 1 else ''}")
            header = f"*{repo_name}* ({', '.join(parts)})"
            lines.append(header)

        # List commits (capped at MAX_COMMITS_PER_REPO)
        for commit in commits[:MAX_COMMITS_PER_REPO]:
            short_hash = commit["hash"][:7]
            message = commit.get("message", "")[:80]
            suffix = " _(recovered)_" if commit.get("recovered") else ""
            lines.append(f"- `{short_hash}` {message}{suffix}")

        if len(commits) > MAX_COMMITS_PER_REPO:
            overflow = len(commits) - MAX_COMMITS_PER_REPO
            lines.append(f"_...and {overflow} more_")

        # List PRs with Slack mrkdwn hyperlinks
        for pr in prs:
            title = pr.get("title", "untitled")[:80]
            url = pr.get("url", "")
            if url:
                lines.append(f"- <{url}|{title}>")
            else:
                lines.append(f"- {title}")

        lines.append("")

    return "\n".join(lines).rstrip()
