"""Tests for bot.agent._format_error_detail -- error reporting for SDK failures."""

from bot.agent import _format_error_detail


CWD = "/home/bot/mic_transformer"


def test_uses_stderr_when_present():
    exc = RuntimeError("Command failed with exit code 1\nCheck stderr output for details")
    detail = _format_error_detail(
        exc, stderr_output="API Error: 401 OAuth token expired", cwd=CWD, exit_code=1,
    )
    assert "API Error: 401 OAuth token expired" in detail
    assert "exit code 1" in detail
    assert CWD in detail
    # Diagnostic hint should NOT appear when we have real stderr
    assert "DIAGNOSTIC" not in detail


def test_falls_back_to_exception_when_stderr_empty():
    exc = ValueError("something went wrong")
    detail = _format_error_detail(exc, stderr_output="", cwd=CWD, exit_code=None)
    assert "ValueError: something went wrong" in detail
    assert CWD in detail


def test_includes_diagnostic_hint_for_opaque_cli_failure():
    """The signature 2026-04-07 incident: SDK raises generic error with the
    'Check stderr output for details' boilerplate, but stderr is empty."""
    exc = Exception("Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for details")
    detail = _format_error_detail(exc, stderr_output="", cwd=CWD, exit_code=None)
    assert "DIAGNOSTIC" in detail
    assert "claude --print" in detail
    assert CWD in detail
    # Should also include the exception type
    assert "Exception:" in detail


def test_includes_chained_cause():
    try:
        try:
            raise ConnectionError("network down")
        except ConnectionError as e:
            raise RuntimeError("wrapper") from e
    except RuntimeError as exc:
        detail = _format_error_detail(exc, stderr_output="", cwd=CWD, exit_code=None)
    assert "RuntimeError: wrapper" in detail
    assert "caused by ConnectionError: network down" in detail


def test_includes_implicit_context():
    try:
        try:
            raise ValueError("inner")
        except ValueError:
            raise RuntimeError("outer")
    except RuntimeError as exc:
        detail = _format_error_detail(exc, stderr_output="", cwd=CWD, exit_code=None)
    assert "RuntimeError: outer" in detail
    assert "during handling of ValueError: inner" in detail


def test_no_diagnostic_when_message_lacks_signature():
    exc = Exception("some other error")
    detail = _format_error_detail(exc, stderr_output="", cwd=CWD, exit_code=None)
    assert "DIAGNOSTIC" not in detail
