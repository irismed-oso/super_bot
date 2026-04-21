"""Tests for the credential update + read fast command regex patterns."""

from bot.fast_commands import _GET_CREDS_RES, _UPDATE_CREDS_RE


def _match_read(text):
    """Run text through the read-path regex list the same way try_fast_command does.

    Returns (payer, location) or (None, None) on no match.
    """
    for idx, pattern in enumerate(_GET_CREDS_RES):
        m = pattern.search(text)
        if not m:
            continue
        if idx == 3:
            return m.group(2).lower(), m.group(1)
        return m.group(1).lower(), m.group(2)
    return None, None


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


class TestGetCredsRegex:
    def test_get_creds_explicit(self):
        assert _match_read("get creds vsp MSOC") == ("vsp", "MSOC")

    def test_show_creds(self):
        assert _match_read("show creds eyemed peg") == ("eyemed", "peg")

    def test_what_is_login_for(self):
        assert _match_read("what is the VSP login for MSOC") == ("vsp", "MSOC")

    def test_what_are_credentials_for(self):
        assert _match_read("what are the eyemed credentials for Beverly") == (
            "eyemed",
            "Beverly",
        )

    def test_whats_password(self):
        assert _match_read("what's the VSP password for Boomtown") == (
            "vsp",
            "Boomtown",
        )

    def test_location_first_order(self):
        assert _match_read("MSOC VSP login") == ("vsp", "MSOC")

    def test_payer_first_with_for(self):
        assert _match_read("VSP credentials for MSOC") == ("vsp", "MSOC")

    def test_case_insensitive(self):
        assert _match_read("GET CREDS VSP msoc") == ("vsp", "msoc")

    def test_does_not_match_update(self):
        # Must NOT false-match the update command.
        assert _match_read("update creds vsp MSOC user pass123") == (None, None)

    def test_does_not_match_update_credentials(self):
        assert _match_read("update credentials eyemed peg jsmith newpass") == (
            None,
            None,
        )

    def test_does_not_match_non_payer(self):
        assert _match_read("what is the aetna login for MSOC") == (None, None)
