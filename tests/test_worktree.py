"""Tests for bot.worktree classifier, branch naming, and create() recovery."""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from bot import worktree


class TestIsCodeTask:
    def test_status_queries_are_readonly(self):
        assert worktree.is_code_task("eyemed status") is False
        assert worktree.is_code_task("vsp status") is False
        assert worktree.is_code_task("bot health") is False

    def test_question_forms_are_readonly(self):
        assert worktree.is_code_task("what is 2 + 2") is False
        assert worktree.is_code_task("how does the crawler work") is False
        assert worktree.is_code_task("explain the fast path") is False

    def test_bare_noun_phrases_are_readonly(self):
        # The 2026-04-08 incident: "eyemed status" was misclassified as
        # a code task, created a worktree, and collided with a stale
        # branch from a previous run.
        assert worktree.is_code_task("eyemed") is False
        assert worktree.is_code_task("audit sync") is False

    def test_explicit_code_verbs_are_code_tasks(self):
        assert worktree.is_code_task("fix the timeout bug") is True
        assert worktree.is_code_task("add retry logic to the crawler") is True
        assert worktree.is_code_task("refactor worktree.py") is True
        assert worktree.is_code_task("implement a new endpoint") is True

    def test_pr_word_boundary(self):
        # "pr" should match "open a pr" but not "prune"
        assert worktree.is_code_task("open a pr for this") is True
        assert worktree.is_code_task("prune stale worktrees") is False


class TestBranchName:
    def test_appends_thread_ts_suffix(self):
        # Repeat invocations of the same phrase must produce distinct
        # branch names so they don't collide with stale branches from
        # prior runs.
        a = worktree.branch_name("eyemed status", "1712345678.111")
        b = worktree.branch_name("eyemed status", "1712345999.222")
        assert a != b
        assert a == "superbot/eyemed-status-1712345678111"
        assert b == "superbot/eyemed-status-1712345999222"

    def test_dots_stripped_from_suffix(self):
        name = worktree.branch_name("fix bug", "1712345678.123456")
        assert "." not in name
        assert name == "superbot/fix-bug-1712345678123456"

    def test_empty_description_still_unique(self):
        name = worktree.branch_name("!!!", "1712345678.1")
        assert name == "superbot/task-17123456781"

    def test_no_thread_ts_preserves_legacy_shape(self):
        assert worktree.branch_name("fix bug") == "superbot/fix-bug"


def _init_repo(path: Path) -> None:
    """Initialize a bare-minimum git repo with one commit."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t"], check=True
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "t"], check=True
    )
    (path / "README").write_text("init\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-qm", "init"], check=True
    )


class TestCreateRecovery:
    """Integration tests for create() against a real git repo."""

    def test_branch_checked_out_elsewhere_surfaces_error(self, monkeypatch):
        # Simulate the 2026-04-08 failure mode: the branch already
        # exists AND is checked out in a stale worktree, so
        # `git branch -D` fails. create() must surface the real
        # reason instead of silently retrying.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "mic_transformer"
            repo.mkdir()
            _init_repo(repo)

            monkeypatch.setattr(worktree, "MIC_TRANSFORMER_PATH", str(repo))
            monkeypatch.setattr(worktree, "WORKTREE_BASE", str(tmp_path))

            # Create a stale worktree holding the branch that the
            # next create() call will want.
            stale_ts = "1111111111.000"
            branch = worktree.branch_name("eyemed status", stale_ts)
            stale_path = tmp_path / f"worktree-stale"
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "add",
                 str(stale_path), "-b", branch],
                check=True,
            )

            # Now call create() with the SAME thread_ts — this is the
            # retry-after-failure case. Branch exists, is checked out,
            # branch -D will fail, and we must see a helpful error.
            with pytest.raises(RuntimeError) as excinfo:
                asyncio.run(worktree.create(stale_ts, "eyemed status"))
            msg = str(excinfo.value)
            assert "branch -D" in msg
            assert branch in msg
            assert "checked out" in msg or "used by worktree" in msg

    def test_happy_path_creates_worktree(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "mic_transformer"
            repo.mkdir()
            _init_repo(repo)

            monkeypatch.setattr(worktree, "MIC_TRANSFORMER_PATH", str(repo))
            monkeypatch.setattr(worktree, "WORKTREE_BASE", str(tmp_path))

            ts = "2222222222.000"
            path = asyncio.run(worktree.create(ts, "fix a bug"))
            assert Path(path).is_dir()
            assert Path(path).name == f"worktree-{ts}"
