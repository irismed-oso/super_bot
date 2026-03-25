"""
Deploy-state persistence, repo configuration, and async git helpers.

Provides:
- REPO_CONFIG: canonical repo names with aliases, directories, and deploy config
- resolve_repo(): alias resolution from user text to (name, config) tuple
- write_deploy_state() / read_and_clear_deploy_state(): JSON file I/O for
  self-deploy recovery (super_bot writes state before restart, reads on startup)
- get_repo_status() / get_deploy_preview(): async git helpers for fast-path commands
"""

import asyncio
import json
import os
import time

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Repo configuration
# ---------------------------------------------------------------------------

REPO_CONFIG = {
    "super_bot": {
        "dir": "/home/bot/super_bot",
        "prefect_deployment": "deploy-superbot",
        "service": "superbot",
        "aliases": ["superbot", "super_bot", "sb"],
        "self_deploy": True,
    },
    "mic_transformer": {
        "dir": "/home/bot/mic_transformer",
        "prefect_deployment": "deploy-mic-transformer",
        "service": None,  # TBD -- needs VM verification
        "aliases": ["mic", "mic_transformer", "mt"],
        "self_deploy": False,
    },
}


def resolve_repo(text: str) -> tuple[str, dict] | None:
    """Resolve a repo name or alias from text to (canonical_name, config_dict).

    Checks all aliases for all repos. Returns None if no match.
    Longer aliases are checked first to avoid partial matches
    (e.g. "mic_transformer" before "mic").
    """
    lower = text.lower()
    # Build flat list of (alias, canonical_name, config) sorted by alias length desc
    candidates = []
    for name, cfg in REPO_CONFIG.items():
        for alias in cfg["aliases"]:
            candidates.append((alias, name, cfg))
    candidates.sort(key=lambda c: len(c[0]), reverse=True)

    for alias, name, cfg in candidates:
        if alias in lower:
            return (name, cfg)
    return None


# ---------------------------------------------------------------------------
# Deploy-state file I/O (self-deploy recovery)
# ---------------------------------------------------------------------------

DEPLOY_STATE_PATH = "/home/bot/.deploy-state.json"

_STALE_SECONDS = 300  # 5 minutes


def write_deploy_state(
    channel: str, thread_ts: str, pre_sha: str, user_id: str
) -> None:
    """Write deploy-state file before triggering self-deploy."""
    state = {
        "channel": channel,
        "thread_ts": thread_ts,
        "pre_sha": pre_sha,
        "user_id": user_id,
        "triggered_at": time.time(),
    }
    with open(DEPLOY_STATE_PATH, "w") as f:
        json.dump(state, f)
    log.info("deploy_state.written", channel=channel, pre_sha=pre_sha)


def read_and_clear_deploy_state() -> dict | None:
    """Read and delete the deploy-state file.

    Returns None if the file is missing, unreadable, or older than 5 minutes.
    """
    if not os.path.isfile(DEPLOY_STATE_PATH):
        return None
    try:
        with open(DEPLOY_STATE_PATH) as f:
            state = json.load(f)
        os.unlink(DEPLOY_STATE_PATH)
        # Stale check
        if time.time() - state.get("triggered_at", 0) > _STALE_SECONDS:
            log.warning("deploy_state.stale", age_s=time.time() - state.get("triggered_at", 0))
            return None
        log.info("deploy_state.read", channel=state.get("channel"))
        return state
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("deploy_state.read_error", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Async git helpers
# ---------------------------------------------------------------------------


async def _git(repo_dir: str, *args: str) -> str:
    """Run a git command in *repo_dir* and return stripped stdout.

    Raises RuntimeError on non-zero exit.
    """
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo_dir,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {err[:300]}")
    return stdout.decode().strip()


async def get_repo_status(repo_name: str) -> dict:
    """Return deploy-relevant status for a configured repo.

    Returns dict with keys: sha, branch, behind, dirty.
    """
    cfg = REPO_CONFIG.get(repo_name)
    if cfg is None:
        raise ValueError(f"Unknown repo: {repo_name}")
    repo_dir = cfg["dir"]

    sha = await _git(repo_dir, "rev-parse", "--short", "HEAD")
    branch = await _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
    await _git(repo_dir, "fetch", "origin", "main", "--quiet")
    behind_str = await _git(repo_dir, "rev-list", "--count", "HEAD..origin/main")
    porcelain = await _git(repo_dir, "status", "--porcelain")

    return {
        "sha": sha,
        "branch": branch,
        "behind": int(behind_str),
        "dirty": bool(porcelain),
    }


async def get_deploy_preview(repo_name: str) -> str:
    """Return the list of commits that would be deployed (HEAD..origin/main).

    Fetches first to ensure accuracy. Returns a user-friendly message
    if already up to date.
    """
    cfg = REPO_CONFIG.get(repo_name)
    if cfg is None:
        raise ValueError(f"Unknown repo: {repo_name}")
    repo_dir = cfg["dir"]

    await _git(repo_dir, "fetch", "origin", "main", "--quiet")
    commits = await _git(repo_dir, "log", "--oneline", "HEAD..origin/main")
    if not commits:
        return "Already on latest -- nothing to deploy."
    return commits
