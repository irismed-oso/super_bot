"""Tests for the stopped-early rendering path and the tool-name milestone fallback.

Regression coverage for the 2026-04-27 incident where the bot rendered
":white_check_mark: Completed" on top of a mid-sentence partial reply and
the heartbeat stayed stuck on "Starting up..." while the agent ran tools.
"""

import asyncio
from types import SimpleNamespace

from bot import progress


class _StubClient:
    """Slack-client double that records chat_postMessage / chat_update calls."""

    def __init__(self):
        self.posts: list[dict] = []
        self.updates: list[dict] = []

    async def chat_postMessage(self, **kwargs):
        self.posts.append(kwargs)
        return {"ts": "1.1"}

    async def chat_update(self, **kwargs):
        self.updates.append(kwargs)
        return {"ok": True}


def test_post_result_renders_stopped_early_when_result_empty():
    client = _StubClient()
    result = {
        "subtype": "success",
        "result": "",
        "partial_texts": ["Let me check the actual crawler logs."],
        "task_text": "are you running into any login issues?",
    }
    asyncio.run(
        progress.post_result(
            client, "C1", "1700000000.0", result, is_code_task=False, duration_s=88,
        )
    )
    assert client.posts, "expected a result message to be posted"
    body = client.posts[0]["text"]
    assert ":warning:" in body
    assert "Stopped early" in body
    assert "Let me check the actual crawler logs." in body
    assert "_Stopped early after 1m 28s_" in body
    # Must not lie with a Completed footer.
    assert "Completed in" not in body


def test_post_result_renders_completed_when_result_present():
    client = _StubClient()
    result = {
        "subtype": "success",
        "result": "the answer is 4",
        "partial_texts": ["the answer is 4"],
        "task_text": "what is 2+2",
    }
    asyncio.run(
        progress.post_result(
            client, "C1", "1700000000.0", result, is_code_task=False, duration_s=10,
        )
    )
    body = client.posts[0]["text"]
    assert "the answer is 4" in body
    assert "_Completed in 0m 10s_" in body
    assert ":warning:" not in body
    assert "Stopped early" not in body


# --- Tool-name milestone fallback ---
#
# We can't easily build real claude_agent_sdk AssistantMessage / ToolUseBlock
# instances in unit tests, so we monkeypatch the symbols progress.py imports
# to reference our lightweight fakes. The callback uses isinstance() against
# those symbols, so this is sufficient.

class _FakeToolUse:
    def __init__(self, name: str, command: str = ""):
        self.name = name
        self.input = {"command": command} if command else {}


class _FakeAssistantMessage:
    def __init__(self, content):
        self.content = content


def _patched_progress(monkeypatch):
    monkeypatch.setattr(progress, "AssistantMessage", _FakeAssistantMessage)
    monkeypatch.setattr(progress, "ToolUseBlock", _FakeToolUse)


def test_make_on_message_advances_last_activity_on_unknown_tool(monkeypatch):
    """MCP / unrecognized tools must move the heartbeat off 'Starting up...'.

    Before this fix, tool-only turns that didn't match _READ_TOOLS / _WRITE_TOOLS
    or the bash patterns left last_activity stuck on its initial value.
    """
    _patched_progress(monkeypatch)

    heartbeat = SimpleNamespace(
        turn_count=0,
        last_activity="Starting up...",
        format_message=lambda: "fmt",
    )
    client = _StubClient()
    progress_msg = {"channel": "C1", "ts": "1.1"}
    cb = progress.make_on_message(client, "C1", "1.1", progress_msg, heartbeat=heartbeat)

    msg = _FakeAssistantMessage([_FakeToolUse("mcp__mic-transformer__eyemed_status")])
    asyncio.run(cb(msg))

    assert heartbeat.last_activity != "Starting up..."
    assert heartbeat.last_activity.startswith("Running ")
    # MCP prefix should be stripped for readability.
    assert "mcp__" not in heartbeat.last_activity
    assert heartbeat.turn_count == 1


def test_make_on_message_recognized_tool_still_uses_specific_label(monkeypatch):
    """The generic fallback must not regress the existing recognized-tool labels."""
    _patched_progress(monkeypatch)

    heartbeat = SimpleNamespace(
        turn_count=0,
        last_activity="Starting up...",
        format_message=lambda: "fmt",
    )
    client = _StubClient()
    cb = progress.make_on_message(
        client, "C1", "1.1", {"channel": "C1", "ts": "1.1"}, heartbeat=heartbeat,
    )

    msg = _FakeAssistantMessage([_FakeToolUse("Read")])
    asyncio.run(cb(msg))
    assert heartbeat.last_activity == "Reading files..."


def test_pretty_tool_name_strips_mcp_prefix():
    assert progress._pretty_tool_name("mcp__mic-transformer__eyemed_status") == "mic-transformer eyemed status"
    assert progress._pretty_tool_name("Read") == "Read"
    assert progress._pretty_tool_name("Bash") == "Bash"
