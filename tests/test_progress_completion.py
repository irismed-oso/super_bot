"""Tests for bot.progress._format_completion -- empty-result fallback."""

from bot.progress import _format_completion


def test_uses_result_text_when_present():
    assert _format_completion("the answer", ["partial1", "partial2"], False) == "the answer"


def test_falls_back_to_last_partial_when_result_empty():
    # SDK's ResultMessage.result is None when the agent's final turn was
    # tool-use only. The actual content is in partial_texts.
    assert _format_completion("", ["first reply", "final reply"], False) == "final reply"


def test_done_when_both_empty():
    assert _format_completion("", [], False) == "Done."
