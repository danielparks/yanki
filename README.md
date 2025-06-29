# Build [Anki] decks from text files containing YouTube URLs

Yanki makes it easy to build and maintain video flashcard decks for [Anki]. It
can use local video or image files, or it can download videos from any source
[yt-dlp] supports, such as YouTube.

## Installation

You will need `ffmpeg` installed to use Yanki. On macOS, install it from
[ffmpeg.org] or [`brew`]. On Linux or Windows, try installing from
[here][yt-dlp ffmpeg].

I recommend using [`uv`] to run Yanki. It can be [installed][uv install] a
number of ways, but through your package manager, e.g. [`brew`], is simplest.

## Usage

This is a Python package that can be run with [`uv`]. You can see all the
commands and options with

```
❯ uv run yanki --help
Usage: yanki [OPTIONS] COMMAND [ARGS]...

  Build Anki decks from text files containing YouTube URLs.

Options:
  -v, --verbose
  --cache DIRECTORY             Path to cache for downloads and media files.
                                [env var: YANKI_CACHE; default:
                                /Users/daniel/.cache/yanki]
  --reprocess / --no-reprocess  Force reprocessing videos.
  -j, --concurrency INTEGER     Number of ffmpeg process to run at once.  [env
                                var: YANKI_CONCURRENCY; default: 8]
  --help                        Show this message and exit.

Commands:
  build                  Build an Anki package from deck files.
  list-notes             List notes in deck files.
  open-videos            Download, process, and open video URLs.
  open-videos-from-file  Download videos listed in a file and open them.
  serve-http             Serve HTML summary of deck on localhost:8000.
  to-html                Generate HTML version of decks.
  to-json                Generate JSON version of decks.
  update                 Update Anki from deck files.
```

## Quick start

Create a simple deck file, e.g. `basic.deck`, to define your flashcards:

```yaml
title: Basic ASL phrases
more: md:From [Lifeprint](https://www.lifeprint.com/)
audio: strip

https://www.youtube.com/watch?v=FHPszRvL9pg What is your name?
https://www.youtube.com/watch?v=zW8cpOVeKZ4 Are you deaf?
https://www.youtube.com/watch?v=xqKENRGkOUQ Are you a student?
```

On macOS and some Linux distros, you can have `yanki` open Anki and start the
import of the new deck:

```
uv run yanki -v update basic.deck
```

Otherwise, you have have it build an `.apkg` file that you can import into Anki:

```
uv run yanki -v build -o basic.apkg basic.deck
```

## Deck file format

There is a reference for the deck file format in [REFERENCE.md][].

## Examples

The [`asl/`][asl] directory contains example `.deck` files that can be used to
build a deck for the vocabulary and phrases in each [Lifeprint.com ASLU][LP]
lesson. See its [README.md][asl] for information about how I chose which signs
to include.

> [!TIP]
> If you are interested in learning American Sign Language, please see Dr. Bill
Vicar’s [Lifeprint.com ASLU][LP]. These decks can help you, but they cannot
replace the Lifeprint lessons and vocabulary pages.
>
> Plus, Lifeprint is full of Dr. Bill’s humor.

## License

Unless otherwise noted, this is dual-licensed under the Apache 2 and MIT
licenses. You may choose to use either.

  * [Apache License, Version 2.0](LICENSE-APACHE)
  * [MIT license](LICENSE-MIT)

Files in the `asl` directory are not licensed for redistribution. Copyright is
somewhat unclear, and at least some of the material is owned by [Dr. William
Vicars][LP].

[Anki]: https://apps.ankiweb.net
[yt-dlp]: https://github.com/yt-dlp/yt-dlp
[ffmpeg.org]: https://www.ffmpeg.org
[`brew`]: https://brew.sh
[yt-dlp ffmpeg]: https://github.com/yt-dlp/FFmpeg-Builds?tab=readme-ov-file#ffmpeg-static-auto-builds
[`uv`]: https://docs.astral.sh/uv/
[uv install]: https://docs.astral.sh/uv/getting-started/installation/
[REFERENCE.md]: REFERENCE.md
[asl]: asl#readme
[LP]: https://www.lifeprint.com
