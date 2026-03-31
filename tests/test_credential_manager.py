"""Tests for bot.credential_manager -- slug conversion, secret ID generation."""

from bot.credential_manager import _to_secret_slug, _secret_id


class TestToSecretSlug:
    def test_simple_uppercase(self):
        assert _to_secret_slug("PEG") == "peg"

    def test_simple_lowercase(self):
        assert _to_secret_slug("ecec") == "ecec"

    def test_with_spaces(self):
        assert _to_secret_slug("Optical Image") == "optical-image"

    def test_with_parentheses(self):
        assert _to_secret_slug("MSOC (Cambridge)") == "msoc-cambridge"

    def test_complex_parens(self):
        assert _to_secret_slug("Optique (2 locations)") == "optique-2-locations"

    def test_hyphenated(self):
        assert _to_secret_slug("Rhode-Vision") == "rhode-vision"


class TestSecretId:
    def test_eyemed(self):
        assert _secret_id("eyemed", "PEG") == "eyemed-creds-peg"

    def test_vsp(self):
        assert _secret_id("vsp", "ECEC") == "vsp-creds-ecec"

    def test_eyemed_with_spaces(self):
        assert _secret_id("eyemed", "Optical Image") == "eyemed-creds-optical-image"
