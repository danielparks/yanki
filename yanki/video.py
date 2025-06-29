import asyncio
import functools
import hashlib
import json
import logging
import math
import re
import shlex
from dataclasses import dataclass
from multiprocessing import cpu_count
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ffmpeg
import yt_dlp

from yanki.errors import ExpectedError
from yanki.utils import (
    NotFileURLError,
    atomic_open,
    chars_in,
    file_not_empty,
    file_url_to_path,
    get_key_path,
)

LOGGER = logging.getLogger(__name__)

STILL_FORMATS = frozenset(["png", "jpeg", "jpg"])
FILENAME_ILLEGAL_CHARS = '/"[]:'
MORE_INFO_VERSION = 2

# For parsing ffmpeg output.
CROPDETECT_RE = re.compile(
    rb"\[Parsed_cropdetect_.* t:(\d+\.\d+) .* crop=(\S+)"
)


class BadURLError(ExpectedError):
    pass


class FFmpegError(RuntimeError):
    def __init__(
        self,
        command="ffmpeg",
        command_line=None,
        stdout=None,
        stderr=None,
        exit_code=None,
    ):
        super().__init__(f"Error running {command}")
        self.command = command
        if command_line:
            self.add_note(f"Command run: {shlex.join(command_line)}")
        self.command_line = command_line
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


@dataclass
class VideoOptions:
    """Options for processing videos."""

    cache_path: Path
    progress: bool = False
    reprocess: bool = False
    concurrency: int = cpu_count()

    @functools.cached_property
    def semaphore(self):
        return asyncio.Semaphore(self.concurrency)


# Example YouTube video URLs:
# https://gist.github.com/rodrigoborgesdeoliveira/987683cfbfcc8d800192da1e73adc486
#
#   https://www.youtube.com/watch?v=n1PjPqcHswk
#   https://youtube.com/watch/lalOy8Mbfdc
def youtube_url_to_id(url_str, url, query):
    """Get YouTube video ID, e.g. lalOy8Mbfdc, from a youtube.com URL."""
    if len(query.get("v", [])) == 1:
        return query["v"][0]

    try:
        path = url.path.split("/")
        if path[0] == "" and path[1] in {"watch", "v"}:
            return path[2]
    except IndexError:
        # Fall through to error.
        pass

    raise BadURLError(f"Unknown YouTube URL format: {url_str}")


# URLs like http://youtu.be/lalOy8Mbfdc
def youtu_be_url_to_id(url_str, url, _query):
    """Get YouTube video ID, e.g. lalOy8Mbfdc, from a youtu.be URL."""
    try:
        path = url.path.split("/")
        if path[0] == "":
            return path[1].split("&")[0]
    except IndexError:
        # Fall through to error.
        pass

    raise BadURLError(f"Unknown YouTube URL format: {url_str}")


def url_to_id(url_str):
    """Turn video URL into an ID string that can be part of a file name."""
    url = urlparse(url_str)
    query = parse_qs(url.query)

    try:
        domain = "." + url.netloc.lower()
        if domain.endswith(".youtube.com"):
            return "youtube=" + youtube_url_to_id(url_str, url, query)
        if domain.endswith(".youtu.be"):
            return "youtube=" + youtu_be_url_to_id(url_str, url, query)
    except BadURLError:
        # Try to load the URL with yt_dlp and see what happens.
        pass

    # FIXME check this against FILENAME_ILLEGAL_CHARS somehow
    return (
        url_str.replace("\\", "\\\\")
        .replace("|", r"\|")
        .replace('"', r"\'")
        .replace("[", r"\(")
        .replace("]", r"\)")
        .replace(":", r"\=")
        .replace("/", "|")
    )


class Video:
    def __init__(
        self,
        url,
        options,
        working_dir=Path(),
        logger=LOGGER,
    ):
        self.url = url
        self.working_dir = working_dir
        self.options = options
        self.logger = logger

        # self.options is read only, and this will be set to false after
        # reprocessing so we don’t do it over and over.
        self.reprocess = options.reprocess

        self.id = url_to_id(url)
        if invalid := chars_in(FILENAME_ILLEGAL_CHARS, self.id):
            invalid = "".join(invalid)
            raise BadURLError(
                f"Invalid characters ({invalid}) in video ID: {self.id!r}"
            )

        self._raw_metadata = None
        self._format = None
        self._strip_audio = False
        self._strip_video = False
        self._clip = None
        self._crop = None
        self._overlay_text = ""
        self._slow = None

        # Only available after finalizing (or calling their generation methods):
        self._cached_more_info = None
        self._cached_parameters = None

    def cached(self, filename):
        return self.options.cache_path / filename

    def info_cache_path(self):
        return self.cached(f"info_{self.id}.json")

    def more_info_cache_path(self):
        return self.cached(
            f"more_info_{self.id}_clip={self.file_safe_clip()}.json"
        )

    def raw_video_cache_path(self):
        return self.cached("raw_" + self.id + "." + self.info()["ext"])

    def raw_metadata_cache_path(self):
        return self.cached(f"ffprobe_raw_{self.id}.json")

    async def processed_video_cache_path_async(self, prefix="processed_"):
        parameters = "_".join(await self.parameters_list_async())

        if len(parameters) > 60 or chars_in(FILENAME_ILLEGAL_CHARS, parameters):
            parameters = hashlib.blake2b(
                parameters.encode(encoding="utf_8"),
                digest_size=16,
                usedforsecurity=False,
            ).hexdigest()
        return self.cached(
            f"{prefix}{self.id}_{parameters}.{self.output_ext()}"
        )

    def _download_info(self):
        try:
            path = file_url_to_path(self.url)
            return {
                "title": path.stem,
                "ext": path.suffix[1:],
            }
        except NotFileURLError:
            pass

        try:
            with self._yt_dlp() as ydl:
                self.logger.info(f"getting info about {self.url!r}")
                return ydl.sanitize_info(
                    ydl.extract_info(self.url, download=False)
                )
        except yt_dlp.utils.YoutubeDLError as error:
            # This is an ExpectedError, so the __cause__ won’t normally be
            # displayed, so it’s included in the message.
            raise BadURLError(
                f"Error downloading {self.url!r}: {error}"
            ) from error

    @functools.cache
    def info(self):
        try:
            with self.info_cache_path().open("r", encoding="utf_8") as file:
                return json.load(file)
        except FileNotFoundError:
            # Either the file wasn’t found or wasn’t valid JSON. We use `pass`
            # to avoid adding this exception to the context of new exceptions.
            pass

        info = self._download_info()
        with atomic_open(self.info_cache_path()) as file:
            json.dump(info, file)
        return info

    def title(self):
        return self.info()["title"]

    def refresh_raw_metadata(self):
        self.logger.debug(f"refresh raw metadata: {self.raw_video()}")
        try:
            self._raw_metadata = ffmpeg.probe(self.raw_video())
        except ffmpeg.Error as error:
            raise FFmpegError(
                command="ffprobe", stdout=error.stdout, stderr=error.stderr
            ) from error

        with atomic_open(self.raw_metadata_cache_path()) as file:
            json.dump(self._raw_metadata, file)

        return self._raw_metadata

    # This will refresh metadata once if it doesn’t find the passed path the
    # first time.
    def raw_metadata(self, *key_path):
        try:
            # FIXME? Track if ffprobe was already run and don’t run it again.
            if self._raw_metadata:
                return get_key_path(self._raw_metadata, key_path)

            metadata_cache_path = self.raw_metadata_cache_path()
            if (
                metadata_cache_path.stat().st_mtime
                >= self.raw_video().stat().st_mtime
            ):
                # Metadata isn’t older than raw video.
                with metadata_cache_path.open("r", encoding="utf_8") as file:
                    self._raw_metadata = json.load(file)
                    return get_key_path(self._raw_metadata, key_path)
        except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
            # Either the file wasn’t found, wasn’t valid JSON, or it didn’t have
            # the key path. We use `pass` here to avoid adding this exception to
            # the context of new exceptions.
            pass

        return get_key_path(self.refresh_raw_metadata(), key_path)

    def get_fps(self):
        for stream in self.raw_metadata("streams"):
            if stream["codec_type"] == "video":
                division = stream["avg_frame_rate"].split("/")
                if len(division) == 0:
                    continue

                fps = float(division.pop(0))
                for divisor in division:
                    fps /= float(divisor)

                return fps

        raise BadURLError(f"Could not get FPS for media URL {self.url!r}")

    # Expects spec without whitespace
    def time_to_seconds(self, spec, on_none=None):
        """Convert a time spec like 1:01.02 or 4F to decimal seconds."""
        if spec == "" or spec is None:
            return on_none

        if isinstance(spec, (float, int)):
            return float(spec)

        if spec[-1] in "Ff":
            # Frame number
            return int(spec[:-1]) / self.get_fps()
        if spec[-1] in "Ss":
            # Second (s), millisecond (ms), or microsecond (us) suffix
            if spec[-2] in "Mm":
                return float(spec[:-2]) / 1_000
            if spec[-2] in "Uuµ":
                return float(spec[:-2]) / 1_000_000
            return float(spec[:-1])

        # [-][HH]:[MM]:[SS.mmm...]
        sign = 1
        if spec.startswith("-"):
            spec = spec[1:]
            sign = -1

        # FIXME? this acccepts 3.3:500:67.8:0:1.2
        sum = 0
        for part in spec.split(":"):
            sum = sum * 60 + float(part)

        return sign * sum

    def cropdetect(self):
        """Detect black borders to crop.

        more_info_async() must be called first.
        """
        more = self.more_info()

        try:
            # FIXME figure out largest crop
            return more["cropdetect"][0][1]
        except (IndexError, KeyError, TypeError):
            return None

    async def load_more_info_async(self):
        """Load more information about the contents of the media.

        This returns a `dict` with keys:
          * `version`: the current version of the more_info algorithm so that
            old data can be invalidated.
          * `cropdetect`:
            * `[(time, "crop"), ...]`, e.g. `[(0.067, "1920:1072:0:4"), ...]`
            * `None`: the video stream was stripped

        https://ayosec.github.io/ffmpeg-filters-docs/7.0/Filters/Video/cropdetect.html
        """
        if not self.wants_video():
            self._cached_more_info = {
                "version": MORE_INFO_VERSION,
                "cropdetect": None,
            }
            return self._cached_more_info

        # Only process the part of the media we care about.
        in_options = self.clip_to_ffmpeg_input_options(self._clip)
        out_options = self.clip_to_ffmpeg_output_options(self._clip)

        video = ffmpeg.input(str(self.raw_video()), **in_options)["v"]
        video = video.filter("cropdetect", round=2)

        (_, err) = await self.run_async(
            video.output("-", format="null", **out_options)
        )
        # FIXME use metadata=mode=print?

        # (time, "crop"), e.g. (2.369, "1920:1072:0:4")
        cropdetect = [
            (float(matches[1]), matches[2].decode("utf_8"))
            for line in err.split(b"\n")
            if (matches := CROPDETECT_RE.search(line))
        ]

        self._cached_more_info = {
            "version": MORE_INFO_VERSION,
            "cropdetect": cropdetect,
        }
        return self._cached_more_info

    async def more_info_async(self):
        if self._cached_more_info:
            return self._cached_more_info

        path = self.more_info_cache_path()
        try:
            with path.open("r", encoding="utf_8") as file:
                self._cached_more_info = json.load(file)
                if self._cached_more_info is not None:
                    # No version is equivalent to version 1.
                    version = self._cached_more_info.get("version", 1)
                    if version == MORE_INFO_VERSION:
                        return self._cached_more_info
                    self.logger.info(
                        f"Discarding more_info with bad version {version!r} "
                        f"(expected {MORE_INFO_VERSION!r}) at {path}"
                    )
                    self._cached_more_info = None
        except FileNotFoundError:
            # Either the file wasn’t found or wasn’t valid JSON. We use `pass`
            # to avoid adding this exception to the context of new exceptions.
            pass

        await self.load_more_info_async()
        with atomic_open(path) as file:
            json.dump(self._cached_more_info, file)
        return self._cached_more_info

    def more_info(self):
        """Get extra information from finalized video."""
        if self._cached_more_info is None:
            raise ValueError("more_info() called on un-finalized Video")
        return self._cached_more_info

    async def finalize_async(self):
        # Ensure that the video is fully processed and that everything can be
        # accessed synchronously.
        await self.more_info_async()
        await self.processed_video_async()
        return self

    def clip(self, start_spec, end_spec):
        start = self.time_to_seconds(start_spec, on_none=0)
        end = self.time_to_seconds(end_spec, on_none=None)
        if end is not None and end - start <= 0:
            raise ValueError(
                "Cannot clip video to 0 or fewer seconds "
                f"({start_spec!r} to {end_spec!r})"
            )
        self._clip = (start, end)

    def snapshot(self, time_spec):
        self._clip = self.time_to_seconds(time_spec, on_none=None)

    def crop(self, crop):
        if crop in {"none", ""}:
            crop = None
        self._crop = crop

    def overlay_text(self, text):
        self._overlay_text = text

    def audio(self, audio):
        self._strip_audio = audio == "strip"

    def video(self, video):
        self._strip_video = video == "strip"

    def slow(self, start=0, end=None, amount=2):
        """Slow (or speed up) part of the video."""
        start = self.time_to_seconds(start, on_none=0)
        end = self.time_to_seconds(end, on_none=None)

        if (end is not None and end == start) or amount == 1:
            # Nothing is affected
            self._slow = None
        else:
            self._slow = (start, end, float(amount))

    def format(self, extension: str | None):
        if extension is None:
            self._format = None
        else:
            self._format = extension.lower()

    def output_ext(self):
        if self._format is not None:
            return self._format
        if self.is_still():
            return "jpeg"
        return "mp4"

    def is_still(self):
        return (
            isinstance(self._clip, float)
            or self._format in STILL_FORMATS
            or "duration" not in self.raw_metadata("format")
        )

    def has_audio(self):
        """If the raw video contains an audio stream."""
        for stream in self.raw_metadata("streams"):
            if stream["codec_type"] == "audio":
                return True
        return False

    def wants_audio(self):
        """If the output should include an audio stream."""
        return (
            not self._strip_audio and self.has_audio() and not self.is_still()
        )

    def has_video(self):
        """If the raw video contains a video stream or image."""
        for stream in self.raw_metadata("streams"):
            if stream["codec_type"] == "video":
                return True
        return False

    def wants_video(self):
        """If the output should include a video stream or image."""
        return not self._strip_video and self.has_video()

    @functools.cache
    def raw_video(self):
        try:
            # If it’s a file:// URL, then there’s no need to cache.
            source_path = self.working_dir / file_url_to_path(self.url)
        except NotFileURLError:
            pass
        else:
            self.logger.info(f"using local raw video {source_path}")
            return source_path

        if "ext" not in self.info():
            raise BadURLError(f"Invalid media URL {self.url!r}")

        path = self.raw_video_cache_path()
        if path.exists() and path.stat().st_size > 0:
            # Already cached, and we can’t check if it’s out of date.
            return path

        self.logger.info(f"downloading raw video to {path}")

        with self._yt_dlp(outtmpl={"default": str(path)}) as ydl:
            # FIXME why not use the in-memory info?
            if error := ydl.download_with_info_file(self.info_cache_path()):
                # FIXME??!
                raise RuntimeError(error)

        return path

    def clip_to_ffmpeg_input_options(self, clip):
        """Input options for ffmpeg based on real clip.

        Used by load_more_info_async() and processed_video_async().
        """
        options = {}
        match clip:
            case None:
                pass
            case float(snapshot_time):
                options["ss"] = snapshot_time
            case (start, end):
                if end is not None:
                    options["t"] = end - start
                if start:
                    options["ss"] = start
            case other:
                raise ValueError(f"parameter may not be {other!r}")

        return options

    def clip_to_ffmpeg_output_options(self, clip):
        """Output options for ffmpeg based on real clip.

        Used by load_more_info_async() and processed_video_async().
        """
        match clip:
            case None | (_, _):
                return {}
            case float(_snapshot_time):
                return {
                    "frames:v": "1",
                    "q:v": "2",  # JPEG quality
                }
            case other:
                raise ValueError(f"parameter may not be {other!r}")

    def file_safe_clip(self):
        """Get the clip in a filesystem safe format. Does not calculate auto."""
        match self._clip:
            case None | (0, None):
                return "none"
            case float(snapshot_time):
                return snapshot_time
            case (float(_) | int(0) as start, None | float(_) as end):
                return f"({start},{end})"  # No space
            case other:
                raise ValueError(f"Unexpected _clip: {other!r}")

    async def actual_crop_async(self):
        if self._crop == "auto":
            await self.more_info_async()
            return self.cropdetect()
        return self._crop

    async def actual_clip_async(self):
        match self._clip:
            case None:
                return None
            case float(snapshot_time):
                return snapshot_time
            case (float(_) | int(0) as start, None | float(_) as end):
                return (start, end)
            case other:
                raise ValueError(f"Unexpected _clip: {other!r}")

    async def parameters_async(self):
        """Get parameters for producing the video as a dict."""
        self._cached_parameters = {}

        if self._strip_audio:
            self._cached_parameters["audio"] = "strip"
        if self._strip_video:
            self._cached_parameters["video"] = "strip"
        if self._crop is not None:
            self._cached_parameters["crop"] = await self.actual_crop_async()
        if self._overlay_text != "":
            self._cached_parameters["overlay_text"] = self._overlay_text
        if self._slow is not None:
            self._cached_parameters["slow"] = self._slow

        match await self.actual_clip_async():
            case float(time):
                self._cached_parameters["snapshot"] = time
            case (start, end):
                self._cached_parameters["clip"] = (start, end)

        return self._cached_parameters

    # FIXME seems like there should be a separate FinalVideo class with this.
    def parameters_list(self):
        """Get video parameters list[str] (finalized version)."""
        if self._cached_parameters is None:
            raise ValueError("parameters_list() called on un-finalized Video")
        return sorted(
            [
                f"{key}={value!r}"
                for key, value in self._cached_parameters.items()
            ]
        )

    async def parameters_list_async(self):
        """Get parameters for producing the video as list[str]."""
        return sorted(
            [
                f"{key}={value!r}"
                for key, value in (await self.parameters_async()).items()
            ]
        )

    async def processed_video_async(self):
        output_path = await self.processed_video_cache_path_async()
        if not self.reprocess and file_not_empty(output_path):
            return output_path

        # Only reprocess once per run.
        self.reprocess = False

        parameters = " ".join(await self.parameters_list_async())
        self.logger.info(f"processing with ({parameters}) to {output_path}")

        clip = await self.actual_clip_async()
        in_options = self.clip_to_ffmpeg_input_options(clip)
        out_options = self.clip_to_ffmpeg_output_options(clip)

        stream = ffmpeg.input(str(self.raw_video()), **in_options)
        output_streams = {}

        if self.wants_video():
            # Video stream is not being stripped
            video = stream["v"]
            if crop := await self.actual_crop_async():
                # FIXME kludge; doesn’t handle named params
                video = video.filter("crop", *crop.split(":"))

            video = video.filter("scale", -2, 500)

            if self._overlay_text:
                video = video.drawtext(
                    text=self._overlay_text,
                    x=20,
                    y=20,
                    font="Arial",
                    fontcolor="white",
                    fontsize=48,
                    box=1,
                    boxcolor="black@0.5",
                    boxborderw=20,
                )

            output_streams["v"] = video

        if self.wants_audio():
            # Audio stream is not being stripped
            audio = stream["a"]
            output_streams["a"] = audio

        output_streams = self._try_apply_slow(output_streams)
        if isinstance(output_streams, dict):
            output_streams = output_streams.values()
        else:
            output_streams = [output_streams]

        with atomic_open(output_path, encoding=None) as file:
            file.close()
            stream = ffmpeg.output(
                *output_streams, file.name, **out_options
            ).overwrite_output()

            await self.run_async(stream)

        return output_path

    async def run_async(self, stream):
        command = stream.compile()
        self.logger.debug(f"Run {shlex.join(command)}")

        async with self.options.semaphore:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

        if process.returncode:
            raise FFmpegError(
                command_line=command,
                stderr=stderr,
                exit_code=process.returncode,
            )
        return stdout, stderr

    # Expect { 'v': video?, 'a' : audio? } depending on if -vn and -an are set.
    def _try_apply_slow(self, streams):  # noqa: C901 PLR0912 (FIXME complex)
        if self._slow is None:
            return streams

        # These are already floats (or None for end):
        (start, end, amount) = self._slow

        wants_video = self.wants_video()
        wants_audio = self.wants_audio()
        parts = []
        i = 0

        if wants_video:
            vsplit = streams["v"].split()
        if wants_audio:
            asplit = streams["a"].asplit()

        if start != 0:
            if wants_video:
                parts.append(
                    vsplit[i]
                    .filter("trim", start=0, end=start)
                    .filter("setpts", "PTS-STARTPTS")
                )
            if wants_audio:
                parts.append(
                    asplit[i]
                    .filter("atrim", start=0, end=start)
                    .filter("asetpts", "PTS-STARTPTS")
                )
            i += 1

        if end is None:
            expression = {"start": start}
        else:
            expression = {"start": start, "end": end}

        if wants_video:
            parts.append(
                vsplit[i]
                .filter("trim", **expression)
                .filter("setpts", "PTS-STARTPTS")
                .setpts(f"{amount}*PTS")
            )
        if wants_audio:
            part = (
                asplit[i]
                .filter("atrim", **expression)
                .filter("asetpts", "PTS-STARTPTS")
            )

            if amount < 0.01:
                # FIXME validate on parse
                raise ValueError("Cannot slow audio by less than 0.01")
            if amount > 2:
                twos_count = math.floor(math.log2(amount))
                for _ in range(twos_count):
                    part = part.filter("atempo", 0.5)
                last_amount = amount / 2**twos_count
                if last_amount != 1:
                    part = part.filter("atempo", 1 / last_amount)
            else:
                part = part.filter("atempo", 1 / amount)

            parts.append(part)
        i += 1

        if end is not None:
            if wants_video:
                parts.append(
                    vsplit[i]
                    .filter("trim", start=end)
                    .filter("setpts", "PTS-STARTPTS")
                )
            if wants_audio:
                parts.append(
                    asplit[i]
                    .filter("atrim", start=end)
                    .filter("asetpts", "PTS-STARTPTS")
                )

        return ffmpeg.concat(*parts, v=int(wants_video), a=int(wants_audio))

    def _yt_dlp(self, **kwargs):
        """Run yt_dlp."""
        return yt_dlp.YoutubeDL(
            {
                "logtostderr": True,
                "noprogress": not self.options.progress,
                "skip_unavailable_fragments": False,
                "quiet": True,
                **kwargs,
            }
        )
