"""Tests for scripts/worktree_gc.py against a real git repo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "worktree_gc.py"


def git(*args: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "mic_transformer"
    repo_path.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo_path)], check=True
    )
    git("config", "user.email", "t@t", cwd=str(repo_path))
    git("config", "user.name", "t", cwd=str(repo_path))
    (repo_path / "README").write_text("init\n")
    git("add", ".", cwd=str(repo_path))
    git("commit", "-qm", "init", cwd=str(repo_path))
    return repo_path


def run_gc(repo: Path, *extra: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def make_worktree(repo: Path, name: str, branch: str) -> Path:
    wt = repo.parent / name
    git("worktree", "add", str(wt), "-b", branch, cwd=str(repo))
    return wt


def age_path(path: Path, days: float) -> None:
    """Backdate path's mtime by `days`."""
    past = time.time() - days * 86400
    os.utime(path, (past, past))


class TestWorktreeGC:
    def test_dry_run_removes_nothing(self, repo: Path) -> None:
        wt = make_worktree(repo, "worktree-111", "superbot/old-task-111")
        age_path(wt, 30)
        # Get the branch even with main, so has_unmerged_commits=False
        report = run_gc(repo, "--max-age-days", "7")
        assert len(report["removed"]) == 1
        assert wt.exists(), "dry-run should not remove anything"

    def test_apply_removes_old_clean_worktree(self, repo: Path) -> None:
        wt = make_worktree(repo, "worktree-222", "superbot/old-task-222")
        age_path(wt, 30)

        report = run_gc(repo, "--max-age-days", "7", "--apply")
        assert len(report["removed"]) == 1
        assert not wt.exists()

        # Branch should also be gone
        branches = git("branch", "--list", cwd=str(repo)).stdout
        assert "superbot/old-task-222" not in branches

    def test_skips_fresh_worktree(self, repo: Path) -> None:
        wt = make_worktree(repo, "worktree-333", "superbot/fresh-333")
        # Don't age it

        report = run_gc(repo, "--max-age-days", "7", "--apply")
        assert len(report["removed"]) == 0
        assert len(report["skipped"]) == 1
        assert "age" in report["skipped"][0]["reason"]
        assert wt.exists()

    def test_skips_dirty_worktree(self, repo: Path) -> None:
        wt = make_worktree(repo, "worktree-444", "superbot/dirty-444")
        (wt / "uncommitted.txt").write_text("wip\n")
        age_path(wt, 30)

        report = run_gc(repo, "--max-age-days", "7", "--apply")
        assert len(report["removed"]) == 0
        assert any("uncommitted" in s["reason"] for s in report["skipped"])
        assert wt.exists()

    def test_skips_unmerged_branch_by_default(self, repo: Path) -> None:
        wt = make_worktree(repo, "worktree-555", "superbot/unmerged-555")
        (wt / "work.txt").write_text("work\n")
        git("add", ".", cwd=str(wt))
        git("commit", "-qm", "work", cwd=str(wt))
        age_path(wt, 30)

        report = run_gc(repo, "--max-age-days", "7", "--apply")
        assert len(report["removed"]) == 0
        assert any("unmerged" in s["reason"] for s in report["skipped"])
        assert wt.exists()

    def test_prune_unmerged_flag_removes_unmerged(self, repo: Path) -> None:
        wt = make_worktree(repo, "worktree-666", "superbot/unmerged-666")
        (wt / "work.txt").write_text("work\n")
        git("add", ".", cwd=str(wt))
        git("commit", "-qm", "work", cwd=str(wt))
        age_path(wt, 30)

        report = run_gc(
            repo, "--max-age-days", "7", "--prune-unmerged", "--apply"
        )
        assert len(report["removed"]) == 1
        assert not wt.exists()

    def test_ignores_non_superbot_worktrees(self, repo: Path) -> None:
        # A worktree not matching the WORKTREE_NAME_PREFIX should be
        # left alone regardless of age.
        wt = make_worktree(repo, "other-worktree", "feature/xyz")
        age_path(wt, 30)

        report = run_gc(repo, "--max-age-days", "7", "--apply")
        assert len(report["removed"]) == 0
        assert wt.exists()
