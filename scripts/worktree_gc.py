#!/usr/bin/env python3
"""Garbage-collect stale SuperBot worktrees.

Each SuperBot code task creates a git worktree under
/home/bot/worktree-<thread_ts>/ holding a superbot/<slug>-<ts> branch.
Worktrees were meant to persist until the PR merged, but read-only
tasks and abandoned code tasks never reach that state, so they
accumulate forever and tie up branches that then collide with future
runs of the same phrase.

This script removes worktrees that are:
  - Older than --max-age-days (default 7).
  - Clean (no uncommitted changes, no untracked files).
  - Not currently checked out by an unmerged branch with commits
    ahead of main (unless --prune-unmerged is passed).

After removing a worktree it also deletes the associated branch if
no other worktree holds it. Failures on one worktree do not stop the
run — each is logged and we continue.

Default mode is dry-run; pass --apply to actually delete.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_REPO = os.environ.get("MIC_TRANSFORMER_CWD", "/home/bot/mic_transformer")
DEFAULT_MAX_AGE_DAYS = 7
WORKTREE_NAME_PREFIX = "worktree-"
BRANCH_PREFIX = "superbot/"


def run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def list_worktrees(repo: str) -> list[dict]:
    """Return worktree records from `git worktree list --porcelain`.

    Each record has keys: path, HEAD, branch (may be missing for
    detached), bare (bool).
    """
    res = run(["git", "worktree", "list", "--porcelain"], cwd=repo)
    if res.returncode != 0:
        raise SystemExit(f"git worktree list failed: {res.stderr}")

    records: list[dict] = []
    current: dict = {}
    for line in res.stdout.splitlines():
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            current["path"] = val
        elif key == "HEAD":
            current["head"] = val
        elif key == "branch":
            current["branch"] = val.replace("refs/heads/", "")
        elif key == "bare":
            current["bare"] = True
    if current:
        records.append(current)
    return records


def is_clean(worktree_path: str) -> bool:
    res = run(["git", "status", "--porcelain"], cwd=worktree_path)
    if res.returncode != 0:
        return False
    return res.stdout.strip() == ""


def worktree_age_days(worktree_path: str) -> float:
    try:
        mtime = os.path.getmtime(worktree_path)
    except OSError:
        return float("inf")
    return (time.time() - mtime) / 86400


def has_unmerged_commits(repo: str, branch: str) -> bool:
    """True if `branch` has commits not reachable from main/HEAD."""
    # Find the default branch to compare against
    res = run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
    )
    base = res.stdout.strip() if res.returncode == 0 else "main"
    res = run(
        ["git", "rev-list", "--count", f"{base}..{branch}"],
        cwd=repo,
    )
    if res.returncode != 0:
        # Can't determine — be conservative and treat as unmerged
        return True
    try:
        return int(res.stdout.strip()) > 0
    except ValueError:
        return True


def remove_worktree(repo: str, path: str, apply: bool) -> tuple[bool, str]:
    if not apply:
        return True, "dry-run: would remove"
    res = run(["git", "worktree", "remove", "--force", path], cwd=repo)
    if res.returncode != 0:
        return False, res.stderr.strip()
    return True, "removed"


def delete_branch(repo: str, branch: str, apply: bool) -> tuple[bool, str]:
    if not apply:
        return True, "dry-run: would delete branch"
    res = run(["git", "branch", "-D", branch], cwd=repo)
    if res.returncode != 0:
        return False, res.stderr.strip()
    return True, "branch deleted"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo", default=DEFAULT_REPO,
        help=f"git repo containing the worktrees (default: {DEFAULT_REPO})",
    )
    ap.add_argument(
        "--max-age-days", type=float, default=DEFAULT_MAX_AGE_DAYS,
        help=f"remove worktrees older than this (default: {DEFAULT_MAX_AGE_DAYS})",
    )
    ap.add_argument(
        "--prune-unmerged", action="store_true",
        help="also remove clean worktrees whose branch has unmerged commits",
    )
    ap.add_argument(
        "--apply", action="store_true",
        help="actually delete (default is dry-run)",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="emit JSON report instead of human-readable",
    )
    args = ap.parse_args()

    try:
        records = list_worktrees(args.repo)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    report = {"removed": [], "skipped": [], "errors": []}

    for rec in records:
        path = rec.get("path", "")
        name = Path(path).name
        branch = rec.get("branch", "")

        # Only touch SuperBot-managed worktrees
        if not name.startswith(WORKTREE_NAME_PREFIX):
            continue
        if rec.get("bare"):
            continue

        age = worktree_age_days(path)
        if age < args.max_age_days:
            report["skipped"].append(
                {"path": path, "reason": f"age {age:.1f}d < {args.max_age_days}d"}
            )
            continue

        if not is_clean(path):
            report["skipped"].append(
                {"path": path, "reason": "uncommitted or untracked changes"}
            )
            continue

        if (
            branch
            and branch.startswith(BRANCH_PREFIX)
            and has_unmerged_commits(args.repo, branch)
            and not args.prune_unmerged
        ):
            report["skipped"].append(
                {"path": path, "branch": branch, "reason": "unmerged commits"}
            )
            continue

        ok, msg = remove_worktree(args.repo, path, args.apply)
        if not ok:
            report["errors"].append({"path": path, "error": msg})
            continue

        entry = {"path": path, "age_days": round(age, 1), "result": msg}
        if branch and branch.startswith(BRANCH_PREFIX):
            bok, bmsg = delete_branch(args.repo, branch, args.apply)
            entry["branch"] = branch
            entry["branch_result"] = bmsg
            if not bok:
                report["errors"].append(
                    {"path": path, "branch": branch, "error": bmsg}
                )
        report["removed"].append(entry)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[worktree_gc {mode}] repo={args.repo} max_age={args.max_age_days}d")
        print(f"  removed: {len(report['removed'])}")
        for r in report["removed"]:
            print(
                f"    - {r['path']} ({r['age_days']}d)"
                + (f" branch={r.get('branch')}" if r.get('branch') else "")
            )
        print(f"  skipped: {len(report['skipped'])}")
        for s in report["skipped"]:
            print(f"    - {s['path']}: {s['reason']}")
        if report["errors"]:
            print(f"  errors: {len(report['errors'])}")
            for e in report["errors"]:
                print(f"    - {e}")

    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
