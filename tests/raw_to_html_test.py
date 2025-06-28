from yanki.field import raw_to_html


def test_easy_url():
    assert (
        raw_to_html("a http://ex/?q=a&t=1#f b\n")
        == 'a <a href="http://ex/?q=a&amp;t=1#f">http://ex/?q=a&amp;t=1#f</a> b'
    )


def test_html():
    assert (
        raw_to_html('html: <b>"hello" &amp; & invalid OK!</a>\n')
        == ' <b>"hello" &amp; & invalid OK!</a>\n'
    )


def test_md_link():
    assert (
        raw_to_html("md:[link](http://ex/?q=a&t=1#f)\n")
        == '<p><a href="http://ex/?q=a&amp;t=1#f">link</a></p>\n'
    )


def test_rst_link():
    assert (
        raw_to_html("rst:`link <http://ex/?q=a&t=1#f>`_\n")
        == '<p><a class="reference external" href="http://ex/?q=a&amp;t=1#f">'
        "link</a></p>\n"
    )
