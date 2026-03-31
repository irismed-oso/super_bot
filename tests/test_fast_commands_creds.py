"""Tests for the credential update fast command regex patterns."""

from bot.fast_commands import _UPDATE_CREDS_RE


class TestUpdateCredsRegex:
    def test_basic_eyemed(self):
        m = _UPDATE_CREDS_RE.search("update creds eyemed peg jsmith pass123")
        assert m
        assert m.group(1) == "eyemed"
        assert m.group(2) == "peg"
        assert m.group(3) == "jsmith"
        assert m.group(4) == "pass123"

    def test_basic_vsp(self):
        m = _UPDATE_CREDS_RE.search("update creds vsp ecec user1 mypass")
        assert m
        assert m.group(1) == "vsp"
        assert m.group(2) == "ecec"

    def test_set_creds_variant(self):
        m = _UPDATE_CREDS_RE.search("set creds eyemed peg user pass")
        assert m

    def test_update_credentials_variant(self):
        m = _UPDATE_CREDS_RE.search("update credentials vsp beverly user pass")
        assert m

    def test_set_credential_variant(self):
        m = _UPDATE_CREDS_RE.search("set credential eyemed ecec user pass")
        assert m

    def test_case_insensitive(self):
        m = _UPDATE_CREDS_RE.search("UPDATE CREDS EYEMED PEG user pass")
        assert m
        assert m.group(1) == "EYEMED"

    def test_no_match_wrong_payer(self):
        m = _UPDATE_CREDS_RE.search("update creds aetna peg user pass")
        assert m is None

    def test_no_match_missing_password(self):
        m = _UPDATE_CREDS_RE.search("update creds eyemed peg user")
        assert m is None

    def test_no_match_missing_username(self):
        m = _UPDATE_CREDS_RE.search("update creds eyemed peg")
        assert m is None
