"""
Git worktree lifecycle management for task isolation.

Code-change tasks run in isolated worktrees (../worktree-{thread_ts})
so concurrent tasks don't conflict on the same branch. Q&A/read-only
tasks run in the main repo with no worktree created.

Worktrees persist until PR merge to support follow-up messages in the
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


def branch_name(task_description: str, thread_ts: str = "") -> str:
    """Slugify task description into a branch name.

    thread_ts is appended so repeat invocations of the same phrase
    (e.g. "eyemed status") don't collide with stale branches left by
    prior runs. Dots in thread_ts are stripped so the result is a
    valid ref.

    Example: ("fix the timeout bug", "1712345678.123456")
        -> "superbot/fix-the-timeout-bug-1712345678123456"
    """
    slug = re.sub(r"[^a-z0-9]+", "-", task_description.lower().strip())
    slug = slug[:40].strip("-")
    if thread_ts:
        suffix = thread_ts.replace(".", "")
        return f"superbot/{slug}-{suffix}" if slug else f"superbot/task-{suffix}"
    return f"superbot/{slug}"


async def create(thread_ts: str, description: str) -> str:
    """Create a worktree for this thread. Returns the worktree path.

    If the worktree already exists (follow-up message in the same thread),
    returns the existing path without running git commands.

    Handles stale branches/worktrees by pruning and deleting conflicting
    branches before retrying.
    """
    path = worktree_path(thread_ts)
    if os.path.exists(path):
        return path

    branch = branch_name(description, thread_ts)

    # Prune stale worktree references first
    await asyncio.create_subprocess_exec(
        "git", "worktree", "prune",
        cwd=MIC_TRANSFORMER_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", path, "-b", branch,
        cwd=MIC_TRANSFORMER_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0 and b"already exists" in stderr:
        # Branch exists from a previous task -- delete it and retry
        await asyncio.create_subprocess_exec(
            "git", "branch", "-D", branch,
            cwd=MIC_TRANSFORMER_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
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


def _word_match(keyword: str, text: str) -> bool:
    """Check if keyword appears as a whole word (or multi-word phrase) in text.

    Prevents false positives like 'pr' matching 'prune' or 'add' matching 'address'.
    Multi-word keywords (e.g. 'pull request') use simple substring matching.
    """
    if " " in keyword:
        return keyword in text
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text))


def is_code_task(prompt: str) -> bool:
    """Heuristic: does this prompt suggest file modification?

    Defaults to False (read-only) when uncertain. Creating worktrees
    for read-only queries is not free: each worktree pins a branch,
    and repeat invocations of the same phrase (e.g. "eyemed status")
    used to collide with stale branches from prior runs and abort the
    task. We'd rather miss an implicit code task and run it in the
    main repo than block every status query.

    Code-change keywords are matched with word boundaries to avoid
    false positives (e.g. "pr" in "prune").
    """
    code_change_keywords = [
        "improve", "fix", "change", "update", "add", "modify", "refactor",
        "implement", "create", "delete", "remove", "write", "edit",
        "make the code", "code change", "commit", "pull request", "pr",
        "rewrite", "optimize", "enhance",
    ]

    lower = prompt.lower()
    return any(_word_match(kw, lower) for kw in code_change_keywords)
