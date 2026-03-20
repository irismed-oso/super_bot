"""
Git worktree lifecycle management for task isolation.

Code-change tasks run in isolated worktrees (../worktree-{thread_ts})
so concurrent tasks don't conflict on the same branch. Q&A/read-only
tasks run in the main repo with no worktree created.

Worktrees persist until MR merge to support follow-up messages in the
same Slack thread.
"""

import asyncio
import os
import re

MIC_TRANSFORMER_PATH = os.environ.get(
    "MIC_TRANSFORMER_CWD", "/home/bot/mic_transformer"
)
WORKTREE_BASE = os.path.dirname(MIC_TRANSFORMER_PATH)


def worktree_path(thread_ts: str) -> str:
    """Return the filesystem path for a thread's worktree."""
    return os.path.join(WORKTREE_BASE, f"worktree-{thread_ts}")


def branch_name(task_description: str) -> str:
    """Slugify task description into a branch name.

    Example: "fix the timeout bug" -> "superbot/fix-the-timeout-bug"
    """
    slug = re.sub(r"[^a-z0-9]+", "-", task_description.lower().strip())
    slug = slug[:40].strip("-")
    return f"superbot/{slug}"


async def create(thread_ts: str, description: str) -> str:
    """Create a worktree for this thread. Returns the worktree path.

    If the worktree already exists (follow-up message in the same thread),
    returns the existing path without running git commands.
    """
    path = worktree_path(thread_ts)
    if os.path.exists(path):
        return path

    branch = branch_name(description)
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", path, "-b", branch,
        cwd=MIC_TRANSFORMER_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {stderr.decode()}")
    return path


async def stash(thread_ts: str) -> None:
    """Stash uncommitted changes in the worktree (on task failure).

    If the worktree doesn't exist, returns immediately. Ignores the
    returncode since stash on a clean tree exits non-zero harmlessly.
    """
    path = worktree_path(thread_ts)
    if not os.path.exists(path):
        return
    await asyncio.create_subprocess_exec(
        "git", "stash", "--include-untracked",
        cwd=path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


def is_code_task(prompt: str) -> bool:
    """Heuristic: does this prompt suggest file modification?

    Conservative: defaults to True (code task) when uncertain because
    worktrees are cheap. Returns False only for clearly read-only prompts.
    """
    readonly_keywords = [
        "what", "why", "how", "explain", "describe", "show me", "list",
        "find", "search", "read", "look at", "check", "tell me",
    ]
    lower = prompt.lower()
    return not any(
        lower.startswith(kw) or f" {kw} " in lower
        for kw in readonly_keywords
    )
