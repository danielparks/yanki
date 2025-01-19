import dataclasses
from dataclasses import field
import functools

from yanki.field import Fragment, Field
from yanki.utils import make_frozen


# Valid variables in note_id format. Used to validate that our code uses the
# same variables in both places they’re needed.
NOTE_VARIABLES = frozenset(
    [
        "deck_id",
        "url",
        "clip",
        "direction",
        "media",
        "text",
        "line_number",
        "source_path",
    ]
)


def find_invalid_format(format, variables):
    """
    Try `format` and return `KeyError` if it uses anything not in `variables`.
    """
    try:
        format.format(**dict.fromkeys(variables, "value"))
        return None
    except KeyError as error:
        return error


@functools.cache
def note_config_directives():
    return set([field.name for field in dataclasses.fields(NoteConfig)])


@dataclasses.dataclass()
class NoteConfig:
    crop: str = ""
    format: str = ""
    more: Field = field(default_factory=Field)
    overlay_text: str = ""
    tags: set[str] = field(default_factory=set)
    slow: None | tuple[str, None | str, float] = None
    trim: None | tuple[str, str] = None
    audio: str = "include"
    video: str = "include"
    note_id: str = "{deck_id} {url} {clip}"

    def set(self, name, value):
        if name in note_config_directives():
            getattr(self, f"set_{name}")(value)
        else:
            raise ValueError(f"Invalid config directive {name!r}")

    def set_crop(self, input):
        self.crop = input

    def set_format(self, input):
        self.format = input

    def set_more(self, input):
        if input.startswith("+"):
            self.more.add_fragment(Fragment(input[1:]))
        else:
            self.more = Field([Fragment(input)])

    def set_overlay_text(self, input):
        if input.startswith("+"):
            self.overlay_text += input[1:]
        else:
            self.overlay_text = input

    def set_tags(self, input):
        new_tags = input.split()
        found_bare_tag = False

        for tag in new_tags:
            if tag.startswith("+"):
                self.tags.add(tag[1:])
                new_tags = None
            elif tag.startswith("-"):
                try:
                    self.tags.remove(tag[1:])
                except KeyError:
                    pass
                new_tags = None
            else:
                # A tag without a + or - prefix, which implies we’re replacing all tags.
                # FIXME: quoting so a tag with a + or - prefix can be used easily.
                found_bare_tag = True

        if found_bare_tag:
            if new_tags is None:
                raise ValueError(
                    f"Invalid mix of changing tags with setting tags: {input.strip()}"
                )
            self.tags = set(new_tags)

    def set_slow(self, slow_spec):
        if slow_spec.strip() == "":
            self.slow = None
            return

        parts = [p.strip() for p in slow_spec.split("*")]
        if len(parts) != 2:
            raise ValueError(f"Invalid slow without '*': {slow_spec}")

        amount = float(parts[1])
        if amount < 0.01:
            raise ValueError(f"Cannot slow by less than 0.01: {slow_spec}")

        parts = [p.strip() for p in parts[0].split("-")]
        if len(parts) != 2:
            raise ValueError(f"Invalid slow without '-': {slow_spec}")

        # FIXME validate that end > start
        start = parts[0]
        if start == "":
            start = "0"

        end = parts[1]
        if end == "":
            end = None

        self.slow = (start, end, amount)

    def set_trim(self, trim):
        if trim == "":
            self.trim = None
        else:
            clip = [part.strip() for part in trim.split("-")]
            if len(clip) != 2:
                raise ValueError(f"trim must be time-time (found {trim!r})")
            self.trim = (clip[0], clip[1])

    def set_audio(self, audio):
        if audio == "include" or audio == "strip":
            self.audio = audio
        else:
            raise ValueError('audio must be either "include" or "strip"')

    def set_video(self, video):
        if video == "include" or video == "strip":
            self.video = video
        else:
            raise ValueError('video must be either "include" or "strip"')

    def set_note_id(self, note_id):
        if error := find_invalid_format(note_id, NOTE_VARIABLES):
            raise ValueError(f"Unknown variable in note_id format: {error}")
        self.note_id = note_id

    def frozen(self):
        data = dataclasses.asdict(self)
        data["tags"] = frozenset(data["tags"])
        return NoteConfigFrozen(**data)

    def generate_note_id(self, **kwargs):
        if NOTE_VARIABLES != set(kwargs.keys()):
            raise KeyError(
                "Incorrect variables passed to generate_note_id()\n"
                f"  got: {sorted(kwargs.keys())}\n"
                f"  expected: {sorted(NOTE_VARIABLES)}\n"
            )
        return self.note_id.format(**kwargs)


NoteConfigFrozen = make_frozen(NoteConfig)
