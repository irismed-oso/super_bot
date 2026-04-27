"""Tests for Heartbeat.finish() stopped_early flag."""

import asyncio

from bot.heartbeat import Heartbeat


class _StubClient:
    def __init__(self):
        self.updates: list[dict] = []

    async def chat_update(self, **kwargs):
        self.updates.append(kwargs)
        return {"ok": True}


def _run(coro):
    return asyncio.run(coro)


def test_finish_default_writes_completed():
    async def scenario():
        hb = Heartbeat()
        client = _StubClient()
        hb.start(client, {"channel": "C1", "ts": "1.1"})
        await hb.finish()
        return client

    client = _run(scenario())
    assert client.updates
    text = client.updates[-1]["text"]
    assert ":white_check_mark:" in text
    assert "Completed in" in text
    assert "Stopped early" not in text


def test_finish_stopped_early_writes_warning():
    async def scenario():
        hb = Heartbeat()
        client = _StubClient()
        hb.start(client, {"channel": "C1", "ts": "1.1"})
        await hb.finish(stopped_early=True)
        return client

    client = _run(scenario())
    assert client.updates
    text = client.updates[-1]["text"]
    assert ":warning:" in text
    assert "Stopped early in" in text
    assert ":white_check_mark:" not in text


def test_finish_idempotent():
    async def scenario():
        hb = Heartbeat()
        client = _StubClient()
        hb.start(client, {"channel": "C1", "ts": "1.1"})
        await hb.finish()
        await hb.finish(stopped_early=True)  # second call should be a no-op
        return client

    client = _run(scenario())
    assert len(client.updates) == 1
