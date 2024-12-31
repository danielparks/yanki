import pytest
from yanki.field import raw_to_html


def test_easy_url():
    assert (
        raw_to_html("foo http://ex/?q=a&t=1#f bar\n")
        == 'foo <a href="http://ex/?q=a&amp;t=1#f">http://ex/?q=a&amp;t=1#f</a> bar'
    )


def test_html():
    assert (
        raw_to_html('html: <b>"hello" &amp; & invalid OK!</a>\n')
        == ' <b>"hello" &amp; & invalid OK!</a>\n'
    )


def test_rst_link():
    assert (
        raw_to_html("rst:`link <http://ex/?q=a&t=1#f>`_\n")
        == '<p><a class="reference external" href="http://ex/?q=a&amp;t=1#f">link</a></p>\n'
    )
