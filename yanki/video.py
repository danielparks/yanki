from ffmpeg import FFmpeg
import yt_dlp
import json
import os
import urllib

YT_DLP_OPTIONS = {
  'quiet': True,
  'skip_unavailable_fragments': False,
}

def yt_url_to_id(url):
  url_info = urllib.parse.urlparse(url)
  query = urllib.parse.parse_qs(url_info.query)
  if len(query['v']) != 1:
    raise ValueError(f"Expected exactly one v parameter in URL: {url}")
  return query['v'][0]

class Logger:
  def __init__(self):
    self.level = 0

  def info(self, message):
    if self.level >= 0:
      print(message)

LOGGER = Logger()

# FIXME cannot be reused
class Video:
  def __init__(self, url, cache_path="."):
    self.url = url
    self.cache_path = cache_path
    self.id = yt_url_to_id(url)
    self._info = None
    self._raw_metadata = None
    self._crop = None
    self._format = None
    self._still = False
    self.input_options = {}
    self.output_options = { "an": None }

  def cached(self, filename):
    return os.path.join(self.cache_path, filename)

  def info_cache_path(self):
    return self.cached(self.id + '_info.json')

  def raw_video_cache_path(self, logger=LOGGER):
    return self.cached(self.id + '_raw.' + self.info(logger=logger)['ext'])

  def raw_metadata_cache_path(self):
    return self.cached(self.id + '_raw_ffprobe.json')

  def processed_video_cache_path(self):
    parameters = "_".join(self.ffmpeg_parameters()).replace("/", "_")
    return self.cached(f"{parameters}_processed.{self.output_ext()}")

  def info(self, logger=LOGGER):
    if self._info is None:
      try:
        with open(self.info_cache_path(), 'r', encoding="utf-8") as file:
          self._info = json.load(file)
      except FileNotFoundError:
        with yt_dlp.YoutubeDL(YT_DLP_OPTIONS.copy()) as ydl:
          logger.info(f"{self.id}: getting info")
          self._info = ydl.extract_info(self.url, download=False)
          with open(self.info_cache_path(), 'w', encoding="utf-8") as file:
            file.write(json.dumps(ydl.sanitize_info(self._info)))
    return self._info

  def title(self, logger=LOGGER):
    return self.info(logger=logger)['title']

  def raw_metadata(self, logger=LOGGER):
    if self._raw_metadata:
      return self._raw_metadata

    path = self.raw_metadata_cache_path()
    try:
      with open(path, 'r', encoding="utf-8") as file:
        self._raw_metadata = json.load(file)
    except FileNotFoundError:
      metadata_json = FFmpeg(executable="ffprobe").input(
          self.raw_video(logger=logger),
          print_format="json",
          show_streams=None,
        ).execute()
      self._raw_metadata = json.loads(metadata_json)

      with open(path, 'wb') as file:
        file.write(metadata_json)

    return self._raw_metadata

  def get_fps(self, logger=LOGGER):
    metadata = self.raw_metadata(logger=logger)

    for stream in metadata['streams']:
      if stream['codec_type'] == 'video':
        division = stream['avg_frame_rate'].split("/")
        if len(division) == 0:
          continue

        fps = float(division.pop(0))
        for divisor in division:
          fps = fps / float(divisor)

        return fps

    raw_path = self.raw_video(logger=logger)
    raise RuntimeError(f"Could not get FPS for video: {raw_path}")

  # FIXME logger
  def parse_time_spec(self, spec):
    if spec.endswith("F"):
      return "%.3f" % (int(spec[:-1])/self.get_fps())
    else:
      return spec

  def clip(self, start_spec, end_spec):
    self.input_options["ss"] = self.parse_time_spec(start_spec)
    self.output_options["to"] = self.parse_time_spec(end_spec)
    self.output_options["copyts"] = None

  def snapshot(self, time_spec):
    self.input_options["ss"] = self.parse_time_spec(time_spec)
    self.output_options["frames:v"] = "1"
    self.output_options["q:v"] = "2" # JPEG quality
    self._still = True

  def crop(self, crop):
    self._crop = crop

  def format(self, extenstion):
    self._format = extenstion

  def output_ext(self):
    if self._format is not None:
      return self._format
    elif self._still:
      return "jpeg"
    else:
      return "mp4"

  def is_still(self):
    return self._still

  def raw_video(self, logger=LOGGER):
    path = self.raw_video_cache_path(logger=logger)
    if os.path.exists(path) and os.stat(path).st_size > 0:
      return path

    logger.info(f"{self.id}: downloading raw video to {path}")
    options = {
      'outtmpl': {
        'default': path,
      },
      **YT_DLP_OPTIONS,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
      # FIXME why not use the in-memory info?
      error_code = ydl.download_with_info_file(self.info_cache_path())
      if error_code:
        # FIXME??!
        raise RuntimeError(error_code)

    return path

  def ffmpeg_input_options(self):
    return self.input_options

  def ffmpeg_output_options(self):
    if "vf" in self.output_options:
      # FIXME?
      raise ValueError("vf output option already set")

    vf = []
    if self._crop:
      vf.append(f"crop={self._crop}")
    vf.append("scale=-2:500")

    return {
      "vf": ",".join(vf),
      **self.output_options,
    }

  def ffmpeg_parameters(self):
    """
    Get most parameters to ffmpeg. Used to identify output for caching.

    Does not include input or output file names, or options like -y.
    """
    parameters = []

    for key, value in self.ffmpeg_input_options().items():
      parameters.append(f"-{key}")
      if value is not None:
        parameters.append(value)

    parameters.append(self.id)

    for key, value in self.ffmpeg_output_options().items():
      parameters.append(f"-{key}")
      if value is not None:
        parameters.append(value)

    return parameters

  def processed_video(self, logger=LOGGER):
    output_path = self.processed_video_cache_path()
    if os.path.exists(output_path) and os.stat(output_path).st_size > 0:
      return output_path

    raw_path = self.raw_video(logger=logger)

    parameters = " ".join(self.ffmpeg_parameters())
    logger.info(f"{parameters}: processing video")

    FFmpeg() \
      .option("y") \
      .input(raw_path, self.ffmpeg_input_options()) \
      .output(output_path, self.ffmpeg_output_options()) \
      .execute()

    return output_path