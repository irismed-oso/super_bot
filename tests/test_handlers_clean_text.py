from bot.handlers import _clean_message_text


def test_plain_mention_stripped():
    assert _clean_message_text("<@U12345> bot health") == "bot health"


def test_labeled_mention_stripped():
    assert _clean_message_text("<@U12345|Claude> bot health") == "bot health"


def test_trailing_sent_using_footer_newline():
    raw = "<@U0AN19JMTNV> bot health\n*Sent using* <@U0A3LP3CR8F|Claude>"
    assert _clean_message_text(raw) == "bot health"


def test_trailing_sent_using_footer_inline():
    raw = "<@U0AN19JMTNV> bot health *Sent using* <@U0A3LP3CR8F|Claude>"
    assert _clean_message_text(raw) == "bot health"


def test_lowercase_sent_using():
    assert _clean_message_text("bot health *sent using* whatever") == "bot health"


def test_no_mention_no_footer_unchanged():
    assert _clean_message_text("what is 2 + 2") == "what is 2 + 2"


def test_multiple_mentions_stripped():
    raw = "<@U12345> ping <@U67890|Bob> now"
    assert _clean_message_text(raw) == "ping  now".strip()


def test_footer_does_not_eat_earlier_asterisks():
    # Legitimate *emphasis* in the body must survive; only the trailing
    # "*Sent using*" block is stripped.
    raw = "<@U12345> please *bold* this *Sent using* <@U67890|Claude>"
    assert _clean_message_text(raw) == "please *bold* this"
