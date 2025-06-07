import asyncio
from dataclasses import dataclass
import ffmpeg
import functools
import hashlib
import json
import logging
import math
from multiprocessing import cpu_count
from pathlib import Path
from os.path import getmtime
import shlex
from urllib.parse import urlparse, parse_qs
import yt_dlp

from yanki.errors import ExpectedError
from yanki.utils import (
    file_url_to_path,
    file_not_empty,
    atomic_open,
    get_key_path,
    chars_in,
    NotFileURL,
)

LOGGER = logging.getLogger(__name__)

STILL_FORMATS = frozenset(["png", "jpeg", "jpg"])
FILENAME_ILLEGAL_CHARS = '/"[]:'


class BadURL(ExpectedError):
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
        super(FFmpegError, self).__init__(f"Error running {command}")
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
    semaphore: asyncio.Semaphore = asyncio.Semaphore(cpu_count())


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
        if path[0] == "" and path[1] in ("watch", "v"):
            return path[2]
    except IndexError:
        # Fall through to error.
        pass

    raise BadURL(f"Unknown YouTube URL format: {url_str}")


# URLs like http://youtu.be/lalOy8Mbfdc
def youtu_be_url_to_id(url_str, url, query):
    """Get YouTube video ID, e.g. lalOy8Mbfdc, from a youtu.be URL."""
    try:
        path = url.path.split("/")
        if path[0] == "":
            return path[1].split("&")[0]
    except IndexError:
        # Fall through to error.
        pass

    raise BadURL(f"Unknown YouTube URL format: {url_str}")


def url_to_id(url_str):
    """Turn video URL into an ID string that can be part of a file name."""
    url = urlparse(url_str)
    query = parse_qs(url.query)

    try:
        domain = "." + url.netloc.lower()
        if domain.endswith(".youtube.com"):
            return "youtube=" + youtube_url_to_id(url_str, url, query)
        elif domain.endswith(".youtu.be"):
            return "youtube=" + youtu_be_url_to_id(url_str, url, query)
    except BadURL:
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


# FIXME cannot be reused
class Video:
    def __init__(
        self,
        url,
        options,
        working_dir=Path("."),
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
            raise BadURL(
                f"Invalid characters ({''.join(invalid)}) in video ID: {self.id!r}"
            )

        self._raw_metadata = None
        self._format = None
        self._crop = None
        self._overlay_text = ""
        self._slow = None
        self.input_options = {}
        self.output_options = {}
        self._parameters = {}

    def cached(self, filename):
        return self.options.cache_path / filename

    def info_cache_path(self):
        return self.cached(f"info_{self.id}.json")

    def raw_video_cache_path(self):
        return self.cached("raw_" + self.id + "." + self.info()["ext"])

    def raw_metadata_cache_path(self):
        return self.cached(f"ffprobe_raw_{self.id}.json")

    def processed_video_cache_path(self, prefix="processed_"):
        parameters = "_".join(self.parameters_list())

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
        except NotFileURL:
            pass

        try:
            with self._yt_dlp() as ydl:
                self.logger.info(f"getting info about {self.url!r}")
                return ydl.sanitize_info(
                    ydl.extract_info(self.url, download=False)
                )
        except yt_dlp.utils.YoutubeDLError as error:
            raise BadURL(f"Error downloading {self.url!r}: {error}")

    @functools.cache
    def info(self):
        try:
            with self.info_cache_path().open("r", encoding="utf_8") as file:
                return json.load(file)
        except FileNotFoundError:
            # Either the file wasn’t found, wasn’t valid JSON, or it didn’t have
            # the key path. We use `pass` here to avoid adding this exception to
            # the context of new exceptions.
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
            )

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
            if getmtime(metadata_cache_path) >= getmtime(self.raw_video()):
                # Metadata isn’t older than raw video.
                with metadata_cache_path.open("r", encoding="utf_8") as file:
                    self._raw_metadata = json.load(file)
                    return get_key_path(self._raw_metadata, key_path)
        except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
            # Either the file wasn’t found, wasn’t valid JSON, or it didn’t have the
            # key path. We use `pass` here to avoid adding this exception to the
            # context of new exceptions.
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
                    fps = fps / float(divisor)

                return fps

        raise BadURL(f"Could not get FPS for media URL {self.url!r}")

    # Expects spec without whitespace
    def time_to_seconds(self, spec, on_none=None):
        """Converts a time spec like 1:01.02 or 4F to decimal seconds."""
        if spec == "" or spec is None:
            return on_none

        if isinstance(spec, float) or isinstance(spec, int):
            return float(spec)

        if spec[-1] in "Ff":
            # Frame number
            return int(spec[:-1]) / self.get_fps()
        elif spec[-1] in "Ss":
            # Second (s), millisecond (ms), or microsecond (us) suffix
            if spec[-2] in "Mm":
                return float(spec[:-2]) / 1_000
            elif spec[-2] in "Uuµ":
                return float(spec[:-2]) / 1_000_000
            else:
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

    def clip(self, start_spec, end_spec):
        start = self.time_to_seconds(start_spec, on_none=0)
        end = self.time_to_seconds(end_spec, on_none=None)

        if end is not None:
            if end - start <= 0:
                raise ValueError(
                    "Cannot clip video to 0 or fewer seconds "
                    "({start_spec!r} to {end_spec!r})"
                )

            self.input_options["t"] = end - start

        # After the validation step.
        if start:
            self.input_options["ss"] = start

        self._parameters["clip"] = (start, end)
        if "snapshot" in self._parameters:
            del self._parameters["snapshot"]

    def snapshot(self, time_spec):
        self.input_options["ss"] = self.time_to_seconds(time_spec, on_none="")
        self.output_options["frames:v"] = "1"
        self.output_options["q:v"] = "2"  # JPEG quality

        self._parameters["snapshot"] = self.input_options["ss"]
        if "clip" in self._parameters:
            del self._parameters["clip"]

    def crop(self, crop):
        self._crop = crop

    def overlay_text(self, text):
        self._overlay_text = text

    def audio(self, audio):
        if audio == "strip":
            self.output_options["an"] = None
            self._parameters["audio"] = "strip"
        else:
            if "an" in self.output_options:
                del self.output_options["an"]
            if "audio" in self._parameters:
                del self._parameters["audio"]

    def video(self, video):
        if video == "strip":
            self.output_options["vn"] = None
            self._parameters["video"] = "strip"
        else:
            if "vn" in self.output_options:
                del self.output_options["vn"]
            if "video" in self._parameters:
                del self._parameters["video"]

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
        elif self.is_still():
            return "jpeg"
        else:
            return "mp4"

    def is_still(self):
        return (
            str(self.output_options.get("frames:v")) == "1"
            or self._format in STILL_FORMATS
            or "duration" not in self.raw_metadata("format")
        )

    def has_audio(self):
        """Does the raw video contain an audio stream?"""
        for stream in self.raw_metadata("streams"):
            if stream["codec_type"] == "audio":
                return True
        return False

    def wants_audio(self):
        """Should the output include an audio stream?"""
        return (
            "an" not in self.output_options
            and self.has_audio()
            and not self.is_still()
        )

    def has_video(self):
        """Does the raw video contain a video stream or image?"""
        for stream in self.raw_metadata("streams"):
            if stream["codec_type"] == "video":
                return True
        return False

    def wants_video(self):
        """Should the output include a video stream or image?"""
        return "vn" not in self.output_options and self.has_video()

    @functools.cache
    def raw_video(self):
        try:
            # If it’s a file:// URL, then there’s no need to cache.
            source_path = self.working_dir / file_url_to_path(self.url)
            self.logger.info(f"using local raw video {source_path}")
            return source_path
        except NotFileURL:
            pass

        if "ext" not in self.info():
            raise BadURL(f"Invalid media URL {self.url!r}")

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

    def ffmpeg_input_options(self):
        return self.input_options

    def ffmpeg_output_options(self):
        if "vf" in self.output_options:
            # FIXME?
            raise ValueError("vf output option already set")

        return self.output_options

    def parameters(self):
        """Get parameters for producing the video as a dict."""
        parameters = self._parameters.copy()

        if self._crop is not None:
            parameters["crop"] = self._crop
        if self._overlay_text != "":
            parameters["overlay_text"] = self._overlay_text
        if self._slow is not None:
            parameters["slow"] = self._slow

        return parameters

    def parameters_list(self):
        """Get parameters for producing the video as list[str]."""
        return [f"{key}={value!r}" for key, value in self.parameters().items()]

    def processed_video(self):
        output_path = self.processed_video_cache_path()
        if not self.reprocess and file_not_empty(output_path):
            return output_path

        return asyncio.run(self.processed_video_async())

    async def processed_video_async(self):
        output_path = self.processed_video_cache_path()
        if not self.reprocess and file_not_empty(output_path):
            return output_path

        # Only reprocess once per run.
        self.reprocess = False

        parameters = " ".join(self.parameters_list())
        self.logger.info(f"processing with ({parameters}) to {output_path}")

        stream = ffmpeg.input(
            str(self.raw_video()), **self.ffmpeg_input_options()
        )
        output_streams = dict()

        if self.wants_video():
            # Video stream is not being stripped
            video = stream["v"]
            if self._crop:
                # FIXME kludge; doesn’t handle named params
                video = video.filter("crop", *self._crop.split(":"))

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
                *output_streams, file.name, **self.ffmpeg_output_options()
            ).overwrite_output()

            await self.run_async(stream)

        return output_path

    def run(self, stream):
        asyncio.run(self.run_async(stream))

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

    # Expect { 'v': video?, 'a' : audio? } depending on if -vn and -an are set.
    def _try_apply_slow(self, streams):
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
            elif amount > 2:
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
        """Run yt_dlp"""
        return yt_dlp.YoutubeDL(
            {
                "logtostderr": True,
                "noprogress": not self.options.progress,
                "skip_unavailable_fragments": False,
                "quiet": True,
                **kwargs,
            }
        )
