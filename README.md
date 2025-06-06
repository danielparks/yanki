# Build [Anki] decks from text files containing YouTube URLs

Yanki makes it easy to build and maintain video flashcard decks for [Anki]. It
can use local video or image files, or it can download videos from any source
[yt-dlp] supports, such as YouTube.

## Usage

You will need `ffmpeg` installed to use Yanki. On macOS, install it from
[ffmpeg.org] or [`brew`]. On Linux or Windows, try installing from
[here][yt-dlp ffmpeg].

This is a Python package that can be run with [`uv`]:

```
uv run yanki build -o out.apkg asl/*.deck
```

That will produce an `out.apkg` file that can be opened by [Anki].

[Anki]: https://apps.ankiweb.net
[yt-dlp]: https://github.com/yt-dlp/yt-dlp
[ffmpeg.org]: https://www.ffmpeg.org
[`brew`]: https://brew.sh
[yt-dlp ffmpeg]: https://github.com/yt-dlp/FFmpeg-Builds?tab=readme-ov-file#ffmpeg-static-auto-builds
[`uv`]: https://docs.astral.sh/uv/

## Examples

The [`asl/`] directory contains example `.deck` files that can be used to build
a deck for the vocabulary and phrases in each [Lifeprint.com ASLU][LP] lesson.
See its [README] for information about how I chose which signs to include.

> [!TIP]
> If you are interested in learning American Sign Language, please see Dr. Bill
Vicar’s [Lifeprint.com ASLU][LP]. These decks can help you, but they cannot
replace the Lifeprint lessons and vocabulary pages.
>
> Plus, Lifeprint is full of Dr. Bill’s humor.

[`asl/`]: asl#readme
[README]: asl#readme
[LP]: https://www.lifeprint.com

## Deck file format

A deck file is composed to **config** lines and **note** lines.

### Notes

Notes are what we call a collection of one or two (flash) cards. For example,
the following line defines a note that is composed of two cards:

    https://www.youtube.com/watch?v=UyfRF3TeLPs YOUR NAME?

The cards are (question → answer):

  * Video → “YOUR NAME?”
  * “YOUR NAME?” → Video

If the text component is left off, Yanki will use the title of the video if it’s
available.

If the line gets too long, you can continue on the following line by indenting
it, for example:

    https://www.youtube.com/watch?v=UDM9KJJtRbE
      YOU DIVORCE-[non-initialized] YOU?

#### Direction (`<-`, `<->`, `->`)

You may customize which cards are generated using a direction sign. For example,
the following will only generate one card, which will first display the video,
then the text:

    https://www.youtube.com/watch?v=_V31e361KV8 -> WHO? (legacy version)

You may also use `<-` for a single card going from text to video, or you may
explicitly set a note to generate both cards with `<->` (this is the default
behavior).

#### Clip (`@time-time`)

Clip the start and/or end of the video. `time` can be a frame (`#F`, e.g.
`32F`), a timestamp (`MM:SS.sss` or just `SS.sss`, e.g. `1:02`), or can be left
blank to mean the natural start or end.

For example, you could specify `@1:00-` to trim 1 minute off the beginning of
the video, or `@0.5-70f` to trim the first half second off the video and then
end the video at the 70th frame (counting from the original video start).

Normally you can’t have two cards with the same video URL in a deck (see
`note_id:` below), but if you specify a clip you can use the same video multiple
times. This is useful if you need to split a video into multiple cards.

For example, [this video](https://www.youtube.com/watch?v=M4AFC4eEjlQ) has all
of the numbers in ASL from 1 to 100. You could make flash cards for 11, 12, and
13 like so:

    https://www.youtube.com/watch?v=M4AFC4eEjlQ @390F-430F 11
    https://www.youtube.com/watch?v=M4AFC4eEjlQ @450F-482F 12
    https://www.youtube.com/watch?v=M4AFC4eEjlQ @505F-545F 13

If you only want to clip the blank or still frames from the beginning or end or
videos, see `trim:` below.

#### Snapshot (`@time`)

You can snapshot a video by specifying a single frame (`@#F`) or a timestamp
(`@MM:SS.sss` or just `@SS.sss`). For example, this generates cards with a still
image from frame 320:

    https://www.youtube.com/watch?v=M4AFC4eEjlQ @320F 9

### Config lines

Config lines set configuration for future notes, unless they’re _inside_ a
note, in which case they set the configuration for that note and nothing else.

```yaml
https://www.youtube.com/watch?v=FHPszRvL9pg note 1
overlay_text: deck
https://www.youtube.com/watch?v=UyfRF3TeLPs note 2
  overlay_text: note
https://www.youtube.com/watch?v=zW8cpOVeKZ4 note 3
```

The above example produces 3 notes (and 6 cards):

  1. note 1, with no overlay text.
  2. note 2, with the overlay text “note”.
  2. note 3, with the overlay text “deck”.

#### `title:` — Deck title

`title` sets the title of the deck. You _must_ set this somewhere in your deck
file. I recommend putting it right at the top for clarity.

#### `group:` — Group notes together for easy configuration

This allows setting configuration on a group of notes without affecting anything
else in the deck. Example:

```yaml
group:
  more: +md:[FIRST](https://www.lifeprint.com/asl101/pages-signs/f/first.htm)
  https://www.youtube.com/watch?v=tZ04_s30aXY FIRST / primary

  tags: +extra
  https://www.youtube.com/watch?v=x9xgoFqsBkE FIRST-PLACE
```

Each config set on the group only applies to the notes after it, so the `more`
line applies to both, and the `tags` line only applies to the last note.

Neither applies to any notes outside the group.

You may nest groups.

#### `more:` — Add more information to answer card

This configuration adds more information to the answer side of the each card
generated by a note. For example:

```yaml
file://video.mp4 text
  more: added context
```

The above generates two cards:

  * _video.mp4_ → “text” “added context”
  * “text” → _video.mp4_ “added context”

You may set content in three formats:

  * No prefix, e.g. `more: some text`. This converts URLs into links and HTML
    escapes everything. Appropriate for plain text.
  * `html:`, e.g. `more: html:<b>text</b>`. This passes the text through (minus
    the “html:” prefix and it is rendered as HTML by Anki.
  * `rst:` This renders the following text as [reStructuredText].
  * `md:` This renders the following text as [CommonMark Markdown].

You may also use a plus before any prefix to append the rendered text to the
whatever has already been set. For example:

```yaml
more: html:<b>First</b>
file://video.mp4 text
  more: +md: _second_
```

The above generates a note with the `more` text set to “**First** _second_”.

[reStructuredText]: https://docutils.sourceforge.io/rst.html
[CommonMark Markdown]: https://commonmark.org

#### `crop:` — Crop visual media

Crop the media to a certain size in _width_:_height_ format. This can be an
absolute pixel value, e.g. `300:500`, or it can be an expression based on `in_h`
and/or `in_w`. For example, `crop: in_h:in_h` will crop the video to a square of
the size of the input height.

See `ffmpeg`’s [`crop` filter](https://ffmpeg.org/ffmpeg-filters.html#crop) for
more possibilities.

Note that Yanki always scales images and videos to be 500px tall while
maintaining their aspect ratio. The scaling happens after cropping.

#### `trim:` — Cut the start and/or end off the video

This is very similar to clip (`@time-time`), which is explained above. It takes
the same parameters.

The difference is that it doesn’t affect the `note_id`. This has two advantages:

1. You can come back and adjust `trim` later and Anki will correctly update the
   existing cards rather than creating a new ones.
2. It can help avoid duplicate videos. If you use slightly different clips for
   the same video URL, Yanki will treat them as distinct cards. If you used
   `trim:` instead, it will flag them as duplicates.

#### `slow:` — Slow down or speed up part of the media

Sometimes a video, or just a part of a video, is too slow or too fast. The
`slow` configuration allows you to fix that. The following slows down the video
to half speed from 0.5 seconds to 1.0 seconds:

```yaml
slow: 0.5-1 *2
```

You can leave off one or both of the times to slow from the start or to the end
of the video. For example, the following speeds up the end of the video
(starting at the 60th frame) by twice:

```yaml
slow: 60F- *0.5
```

`slow` can only be applied to one part of a video (or audio track).

#### `note_id:` — Note GUIDs

Anki uses the GUID (Globally Unique ID) field to identify notes for update.
By default, Yanki generates GUIDs based on the deck ID (generated from the deck
title), the video URL, and the clip of the video (e.g. `@0:01-0:02`).

You can customize how the GUID is generated with the `note_id` configuration:

```yaml
# Default:
note_id: {deck_id} {url} {clip}

# Use the text that corresponds to the video:
note_id: {deck_id} {text}
```

Leaving out `{deck_id}` can be useful if you might need to move notes between
decks later on. Unfortunately, Anki’s import will not actually move notes from
one deck to another, but it will update them in the other deck. You can then
move them manually. This is useful if you want to keep your study progress.

If you do leave out `{deck_id}`, you should probably include something else to
make sure the GUID is unique outside of your decks. For example:

```yaml
title: Really Cool Cards::subdeck 1
note_id: Really Cool Cards {url} {clip}
```

#### Other configs

There are a few other configuration options:

  * `format:`: The file extension of the media to generate (default: `mp4`)
  * `overlay_text:`: Set overlay text to appear on the video
  * `tags:`: Set tags for notes (divided by spaces)
  * `audio:`: `include` (default) or `strip` (remove from media)
  * `video:`: `include` (default) or `strip` (remove from media)

## Example deck

```yaml
title: Lifeprint ASL::Phrases::Phrases 01
overlay_text: Phrase
more: md:From [Lifeprint](https://www.lifeprint.com/)
  ASLU [lesson 1](https://www.lifeprint.com/asl101/lessons/lesson01.htm)
tags: Lifeprint lesson_01 phrase
audio: strip

https://www.youtube.com/watch?v=FHPszRvL9pg YOU what-NAME?
https://www.youtube.com/watch?v=UyfRF3TeLPs YOUR NAME?
https://www.youtube.com/watch?v=zW8cpOVeKZ4 DEAF YOU?
https://www.youtube.com/watch?v=xqKENRGkOUQ STUDENT YOU?
https://www.youtube.com/watch?v=OYvy_O_hhfw YOU UNDERSTAND THEM?

# You can extend a line by inserting tabs or spaces before any text:
https://www.youtube.com/watch?v=wskcwTX27RU
  INDEX-[that-person] WHO?

  (Who is that person?)
https://www.youtube.com/watch?v=l0nVGVuHHB8 AGAIN, NAME YOU?

# These cards are similar, but distinct:
https://www.youtube.com/watch?v=0Kvv6FpF348 YOUR TEACHER what-NAME?
https://www.youtube.com/watch?v=Th7pOg8YbCU YOUR TEACHER NAME WHAT?

# You can change tags used for future tags at any time:
tags: Lifeprint lesson_01 vocabulary extra
https://www.youtube.com/watch?v=b_qv-0Jbqn0 CLEAN-UP
```
