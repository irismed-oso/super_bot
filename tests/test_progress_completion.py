"""Tests for bot.progress._format_completion -- empty-result fallback."""

from bot.progress import _format_completion, is_stopped_early


def test_uses_result_text_when_present():
    assert _format_completion("the answer", ["partial1", "partial2"], False) == "the answer"


def test_falls_back_to_last_partial_when_result_empty():
    # SDK's ResultMessage.result is None when the agent's final turn was
    # tool-use only. The actual content is in partial_texts.
    assert _format_completion("", ["first reply", "final reply"], False) == "final reply"


def test_done_when_both_empty():
    assert _format_completion("", [], False) == "Done."


# is_stopped_early -- distinguishes "real success" from "SDK said done but
# the agent never produced a closing assistant text." The latter is what
# happened on 2026-04-27 when the bot rendered ":white_check_mark: Completed"
# on top of a mid-sentence "Let me check the actual crawler logs."

def test_is_stopped_early_false_when_result_text_present():
    assert is_stopped_early({"subtype": "success", "result": "the answer", "partial_texts": []}) is False


def test_is_stopped_early_true_when_result_empty_with_partials():
    assert is_stopped_early({
        "subtype": "success",
        "result": "",
        "partial_texts": ["Let me check the actual crawler logs."],
    }) is True


def test_is_stopped_early_false_when_no_partials():
    assert is_stopped_early({"subtype": "success", "result": "", "partial_texts": []}) is False


def test_is_stopped_early_false_for_error_subtypes():
    # Errors get their own formatting; don't double-tag them as stopped_early.
    for subtype in ("error_timeout", "error_cancelled", "error_internal"):
        assert is_stopped_early({
            "subtype": subtype,
            "result": "",
            "partial_texts": ["something"],
        }) is False
