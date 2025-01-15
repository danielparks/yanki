from yanki.field import URL_REGEX


def find_url(input):
    return URL_REGEX.search(input)[0]


def test_easy_url():
    assert (
        find_url("foo bar https://example.com/?q=abc&t=1#fragment hey")
        == "https://example.com/?q=abc&t=1#fragment"
    )


def test_easy_url_empty_fragment():
    assert (
        find_url("foo bar https://example.com/?q=abc&t=1# hey")
        == "https://example.com/?q=abc&t=1#"
    )


def test_easy_url_uppercase():
    assert (
        find_url("foo bar HTTPS://EXAMPLE.com/?q=abc&t=1#FRAGMENT hey")
        == "HTTPS://EXAMPLE.com/?q=abc&t=1#FRAGMENT"
    )


def test_newline_url():
    assert (
        find_url("foo bar\nhttps://example.com/?q=abc&t=1#fragment\nhey")
        == "https://example.com/?q=abc&t=1#fragment"
    )


def test_bare_url():
    assert (
        find_url("https://example.com/?q=abc&t=1#fragment")
        == "https://example.com/?q=abc&t=1#fragment"
    )


def test_bare_url_empty_fragment():
    assert (
        find_url("https://example.com/?q=abc&t=1#")
        == "https://example.com/?q=abc&t=1#"
    )


def test_trailing_comma():
    assert (
        find_url("foo https://example.com/?q=abc&t=1, bar")
        == "https://example.com/?q=abc&t=1"
    )


def test_trailing_period():
    assert (
        find_url("foo https://example.com/?q=abc&t=1. bar")
        == "https://example.com/?q=abc&t=1"
    )


def test_trailing_question_mark():
    assert find_url("foo https://example.com/? bar") == "https://example.com/"


def test_trailing_colon():
    assert find_url("foo https://example.com/:\nbar") == "https://example.com/"


def test_preceeding_lt():
    assert find_url("<https://example.com/ more") == "https://example.com/"


def test_lt_gt():
    assert find_url("<https://example.com/> more") == "https://example.com/"


def test_square_brackets():
    assert find_url("[https://example.com/] more") == "https://example.com/"


def test_parentheses():
    assert find_url("(https://example.com/) more") == "https://example.com/"


# Example: https://en.wikipedia.org/wiki/Wikipedia_(disambiguation)
def test_wiki_url():
    assert find_url("http://wiki/a(b)") == "http://wiki/a(b)"


def test_parentheses_around_wiki_url():
    assert find_url("(http://wiki/a(b))") == "http://wiki/a(b)"


def test_parenthesis_before_wiki_url():
    # Not ideal, but unavoidable, I think.
    assert find_url("(http://wiki/a(b) more)") == "http://wiki/a(b"


def test_parenthesis_after_wiki_url():
    # Not ideal, but unavoidable, I think.
    assert find_url("(foo http://wiki/a(b))") == "http://wiki/a(b))"
