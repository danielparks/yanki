import functools
import html
import os
import re
from urllib.parse import quote

import docutils.core
import mistletoe

# Regular expression to find http:// URLs in text.
URL_REGEX = re.compile(
    r"""
    # URL with no surrounding parentheses
    (?<!\() \b(https?://[.?!,;:a-z0-9$_+*\'()/&=@#-]*[a-z0-9$_+*\'()/&=@#-])
    # URL with surrounding parentheses
    | (?<=\() (https?://[.?!,;:a-z0-9$_+*\'()/&=@#-]*[a-z0-9$_+*\'()/&=@#-]) (?=\))
    # URL with an initial parenthesis
    | (?<=\() (https?://[.?!,;:a-z0-9$_+*\'()/&=@#-]*[a-z0-9$_+*\'()/&=@#-]) (?!\))
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def rst_to_html(rst):
    # From https://wiki.python.org/moin/reStructuredText#The_.22Cool.22_Way
    parts = docutils.core.publish_parts(source=rst, writer_name="html5")
    return parts["body_pre_docinfo"] + parts["fragment"]


@functools.cache
def raw_to_html(raw):
    if raw.startswith("md:"):
        return mistletoe.markdown(raw[3:])
    elif raw.startswith("rst:"):
        return rst_to_html(raw[4:])
    elif raw.startswith("html:"):
        return raw[5:]
    else:
        return (
            URL_REGEX.sub(r'<a href="\1">\1</a>', html.escape(raw))
            .rstrip()
            .replace("\n", "<br/>")
        )


class Fragment:
    def __init__(self, raw):
        self.raw = raw

    def media(self):
        return []

    def media_paths(self):
        return []

    def render_anki(self):
        return self.render_html("")

    def render_html(self, base_path=""):
        return raw_to_html(self.raw)

    def __str__(self):
        return self.render_anki()

    def __repr__(self):
        return repr(self.render_anki())


class MediaFragment(Fragment):
    def __init__(self, path, media):
        self.path = path
        self._media = media

    def file_name(self):
        return os.path.basename(self.path)

    def path_in_base(self, base_path):
        return

    def anki_filename(self):
        """Get the filename encoded for Anki."""
        # FIXME need to prevent characters that break Anki.
        # html.escape() breaks Anki. A literal single quote (') is escaped as
        # &#x27;, which then gets transformed to &amp;%23x27; at some point.
        return self.file_name()

    def html_path_in_base(self, base_path):
        """
        Get the path relative to base_path, and encoded for HTML.

        base_path may be a URL or a relative path. It must already be URL
        encoded, but must not escaped for HTML.
        """
        return html.escape(
            os.path.join(base_path, quote(self.file_name(), encoding="utf_8"))
        )

    def media(self):
        return [self._media]

    def media_paths(self):
        return [str(self.path)]


class ImageFragment(MediaFragment):
    def render_anki(self):
        return f'<img src="{self.anki_filename()}" />'

    def render_html(self, base_path=""):
        return f'<img src="{self.html_path_in_base(base_path)}" />'


class VideoFragment(MediaFragment):
    def render_anki(self):
        return f"[sound:{self.anki_filename()}]"

    def render_html(self, base_path="."):
        return (
            "<video controls playsinline "
            f'src="{self.html_path_in_base(base_path)}"></video>'
        )


class Field:
    def __init__(self, fragments: list[Fragment] = []):
        self.fragments = fragments

    def add_fragment(self, fragment: Fragment):
        self.fragments.append(fragment)

    def media(self):
        for fragment in self.fragments:
            yield from fragment.media()

    def media_paths(self):
        for fragment in self.fragments:
            yield from fragment.media_paths()

    def render_anki(self):
        return "".join([fragment.render_anki() for fragment in self.fragments])

    def render_html(self, base_path=""):
        return "".join(
            [fragment.render_html(base_path) for fragment in self.fragments]
        )

    def __str__(self):
        return self.render_anki()

    def __repr__(self):
        return repr([fragment for fragment in self.fragments])
