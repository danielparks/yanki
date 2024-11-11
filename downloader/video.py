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
    self.output_id = [self.id]
    self._info = None
    self.crop = None
    self.input_options = {}
    self.output_options = { "an": None }
    self.output_ext = "mp4"

  def cached(self, filename):
    return os.path.join(self.cache_path, filename)

  def info_cache_path(self):
    return self.cached(self.id + '_info.json')

  def raw_video_cache_path(self, logger=LOGGER):
    return self.cached(self.id + '_raw.' + self.info(logger=logger)['ext'])

  def processed_video_cache_path(self):
    output_id = "_".join(self.output_id)
    return self.cached(f"{output_id}_processed.{self.output_ext}")

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

  def get_fps(self):
    #### FIXME
    return 29.97

  def parse_time_spec(self, spec):
    if spec.endswith("F"):
      return "%.3f" % (int(spec[:-1])/self.get_fps())
    else:
      return spec

  def clip(self, start_spec, end_spec):
    self.input_options["ss"] = self.parse_time_spec(start_spec)
    self.output_options["to"] = self.parse_time_spec(end_spec)
    self.output_options["copyts"] = None
    self.output_id.append(f"ss{self.input_options['ss']}")
    self.output_id.append(f"to{self.output_options['to']}")

  def snapshot(self, time_spec):
    self.input_options["ss"] = self.parse_time_spec(time_spec)
    self.output_options["frames:v"] = "1"
    self.output_options["q:v"] = "2" # JPEG quality
    self.output_ext = "jpeg"
    self.output_id.append(f"ss{self.input_options['ss']}")

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

  def processed_video(self, logger=LOGGER):
    output_path = self.processed_video_cache_path()
    if os.path.exists(output_path) and os.stat(output_path).st_size > 0:
      return output_path

    raw_path = self.raw_video(logger=logger)

    if "fv" in self.output_options:
      # FIXME?
      raise ValueError("vf output option already set")

    vf = []
    if self.crop:
      vf.append(f"crop={self.crop}")
    vf.append("scale=-2:500")
    self.output_options["vf"] = ",".join(vf)

    output_id = " ".join(self.output_id)
    logger.info(f"{output_id}: processing video")
    FFmpeg().option("y").input(
      raw_path,
      self.input_options,
    ).output(
      output_path,
      self.output_options,
    ).execute()

    return output_path
