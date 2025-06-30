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

There is a reference for the deck file format in [REFERENCE.md][].

[REFERENCE.md]: REFERENCE.md

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
