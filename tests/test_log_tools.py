"""Tests for bot.log_tools -- structlog parsing, secret scrubbing, truncation, alias resolution."""

import json

from bot.log_tools import (
    format_log_output,
    parse_structlog_line,
    resolve_service_name,
    scrub_secrets,
)


# ---------------------------------------------------------------------------
# parse_structlog_line
# ---------------------------------------------------------------------------


class TestParseStructlogLine:
    def test_plain_text_passthrough(self):
        line = "Mar 25 10:00:00 vm superbot[123]: Starting up"
        assert parse_structlog_line(line) == line

    def test_empty_line(self):
        assert parse_structlog_line("") == ""
        assert parse_structlog_line("  ") == ""

    def test_json_structlog_basic(self):
        data = {"timestamp": "2026-03-25T10:00:00Z", "level": "info", "event": "server.started"}
        result = parse_structlog_line(json.dumps(data))
        assert "2026-03-25T10:00:00Z" in result
        assert "INFO" in result
        assert "server.started" in result

    def test_json_structlog_with_extras(self):
        data = {
            "timestamp": "2026-03-25T10:00:00Z",
            "level": "error",
            "event": "request.failed",
            "status": 500,
            "path": "/api/test",
        }
        result = parse_structlog_line(json.dumps(data))
        assert "ERROR" in result
        assert "request.failed" in result
        assert "status=500" in result
        assert "path=/api/test" in result

    def test_invalid_json(self):
        line = "{not valid json"
        assert parse_structlog_line(line) == line

    def test_json_without_event(self):
        """JSON without event key should pass through."""
        data = {"foo": "bar", "count": 42}
        line = json.dumps(data)
        assert parse_structlog_line(line) == line

    def test_skips_logger_lineno_keys(self):
        data = {
            "timestamp": "2026-03-25T10:00:00Z",
            "level": "info",
            "event": "test",
            "logger": "bot.agent",
            "lineno": 42,
        }
        result = parse_structlog_line(json.dumps(data))
        assert "logger=" not in result
        assert "lineno=" not in result


# ---------------------------------------------------------------------------
# scrub_secrets
# ---------------------------------------------------------------------------


class TestScrubSecrets:
    def test_slack_bot_token(self):
        text = "token: xoxb-123456789012-abcdefghij"
        result = scrub_secrets(text)
        assert "xoxb-" not in result
        assert "[REDACTED]" in result

    def test_slack_user_token(self):
        text = "xoxp-1234567890123-abcdefghijk"
        result = scrub_secrets(text)
        assert "xoxp-" not in result

    def test_sk_api_key(self):
        text = "api_key=sk-abcdefghijklmnopqrstuvwxyz1234567890"
        result = scrub_secrets(text)
        assert "sk-abcdef" not in result

    def test_aws_access_key(self):
        text = "AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE"
        result = scrub_secrets(text)
        assert "AKIAIOSF" not in result

    def test_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        result = scrub_secrets(text)
        assert "eyJhbG" not in result
        assert "Bearer [REDACTED]" in result

    def test_password_in_url(self):
        text = "postgresql://user:secretpass123@db.example.com:5432/mydb"
        result = scrub_secrets(text)
        assert "secretpass123" not in result
        assert "[REDACTED]" in result

    def test_no_false_positive_short_strings(self):
        """Short strings should not be scrubbed."""
        text = "status=ok count=42 name=test"
        assert scrub_secrets(text) == text

    def test_generic_api_key_value(self):
        text = "api_key=super_secret_value_12345678"
        result = scrub_secrets(text)
        assert "super_secret" not in result


# ---------------------------------------------------------------------------
# format_log_output
# ---------------------------------------------------------------------------


class TestFormatLogOutput:
    def test_short_output_unchanged(self):
        raw = "line1\nline2\nline3"
        result = format_log_output(raw, max_chars=2800)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result
        assert "showing last" not in result

    def test_truncation_keeps_recent(self):
        # Create output that exceeds limit
        lines = [f"line-{i}: " + "x" * 50 for i in range(100)]
        raw = "\n".join(lines)
        result = format_log_output(raw, max_chars=500)
        assert "showing last" in result
        assert "of 100 lines" in result
        # Most recent lines should be present
        assert "line-99" in result
        # Oldest lines should be truncated
        assert "line-0" not in result

    def test_truncation_respects_limit(self):
        lines = [f"line-{i}: data" for i in range(200)]
        raw = "\n".join(lines)
        result = format_log_output(raw, max_chars=500)
        assert len(result) <= 560  # allow small overhead for header

    def test_secrets_scrubbed_in_output(self):
        raw = "normal line\ntoken: xoxb-1234567890-abcdefghij\nanother line"
        result = format_log_output(raw)
        assert "xoxb-" not in result
        assert "[REDACTED]" in result

    def test_structlog_lines_parsed(self):
        data = {"timestamp": "2026-03-25T10:00:00Z", "level": "info", "event": "test.event"}
        raw = json.dumps(data) + "\nplain text line"
        result = format_log_output(raw)
        assert "INFO" in result
        assert "test.event" in result
        assert "plain text line" in result


# ---------------------------------------------------------------------------
# resolve_service_name
# ---------------------------------------------------------------------------


class TestResolveServiceName:
    def test_superbot_alias(self):
        assert resolve_service_name("superbot") == "superbot"

    def test_sb_alias(self):
        assert resolve_service_name("sb") == "superbot"

    def test_super_bot_alias(self):
        assert resolve_service_name("super_bot") == "superbot"

    def test_mic_alias(self):
        # mic_transformer has service=None, should fall back to canonical name
        result = resolve_service_name("mic")
        assert result is not None

    def test_unknown_service(self):
        assert resolve_service_name("nonexistent") is None

    def test_case_insensitive(self):
        assert resolve_service_name("SuperBot") == "superbot"
        assert resolve_service_name("SUPERBOT") == "superbot"
