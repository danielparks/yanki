import ffmpeg
import hashlib
import json
import logging
import os
import sys
import urllib.parse
import yt_dlp

LOGGER = logging.getLogger(__name__)

YT_DLP_OPTIONS = {
  'quiet': True,
  'skip_unavailable_fragments': False,
}

class BadURL(ValueError):
  pass

# Example YouTube video URLs:
# https://gist.github.com/rodrigoborgesdeoliveira/987683cfbfcc8d800192da1e73adc486
#
#   https://www.youtube.com/watch?v=n1PjPqcHswk
#   https://youtube.com/watch/lalOy8Mbfdc
def youtube_url_to_id(url_str, url, query):
  """Get YouTube video ID, e.g. lalOy8Mbfdc, from a youtube.com URL."""
  if len(query.get('v', [])) == 1:
    return query['v'][0]

  try:
    path = url.path.split('/')
    if path[0] == '' and path[1] in ('watch', 'v'):
      return path[2]
  except IndexError:
    # Fall through to error.
    pass

  raise BadURL(f'Unknown YouTube URL format: {url_str}')

# URLs like http://youtu.be/lalOy8Mbfdc
def youtu_be_url_to_id(url_str, url, query):
  """Get YouTube video ID, e.g. lalOy8Mbfdc, from a youtu.be URL."""
  try:
    path = url.path.split('/')
    if path[0] == '':
      return path[1].split('&')[0]
  except IndexError:
    # Fall through to error.
    pass

  raise BadURL(f'Unknown YouTube URL format: {url_str}')

def url_to_id(url_str):
  """Turn video URL into an ID string that can be part of a file name."""
  url = urllib.parse.urlparse(url_str)
  query = urllib.parse.parse_qs(url.query)

  try:
    domain = '.' + url.netloc.lower()
    if domain.endswith('.youtube.com'):
      return 'youtube:' + youtube_url_to_id(url_str, url, query)
    elif domain.endswith('.youtu.be'):
      return 'youtube:' + youtu_be_url_to_id(url_str, url, query)
  except BadURL:
    # Try to load the URL with yt_dlp and see what happens.
    pass

  return url_str.replace('|', '||').replace('/', '|')

NON_ZERO_DIGITS = set('123456789')
def is_non_zero_time(time_spec):
  for c in time_spec:
    if c in NON_ZERO_DIGITS:
      return True
  return False

# FIXME cannot be reused
class Video:
  def __init__(self, url, cache_path="."):
    self.url = url
    self.cache_path = cache_path
    self._info = None
    self._raw_metadata = None
    self._format = None
    self._still = False

    # ffmpeg parameters. Every run with the same parameters should produce the
    # same video (assuming the source hasn’t changed).
    self.id = url_to_id(url)
    if '/' in self.id:
      raise BadURL(f'Invalid "/" in video ID: {repr(self.id)}')
    self._crop = None
    self._overlay_text = ''
    self._slow_filter = None
    self.input_options = {}
    self.output_options = {}

  def cached(self, filename):
    return os.path.join(self.cache_path, filename)

  def info_cache_path(self):
    return self.cached(f'info_{self.id}.json')

  def raw_video_cache_path(self):
    return self.cached('raw_' + self.id + '.' + self.info()['ext'])

  def raw_metadata_cache_path(self):
    return self.cached(f'ffprobe_raw_{self.id}.json')

  def processed_video_cache_path(self, prefix='processed_'):
    parameters = '_'.join(self.ffmpeg_parameters())

    if '/' in parameters or len(parameters) > 60:
      LOGGER.debug(f'hashing parameters {repr(parameters)}')
      parameters = hashlib.blake2b(
        parameters.encode(encoding='utf-8'),
        digest_size=16,
        usedforsecurity=False).hexdigest()
    return self.cached(f"{prefix}{parameters}.{self.output_ext()}")

  def info(self):
    if self._info is None:
      try:
        with open(self.info_cache_path(), 'r', encoding="utf-8") as file:
          self._info = json.load(file)
      except FileNotFoundError:
        try:
          with yt_dlp.YoutubeDL(YT_DLP_OPTIONS.copy()) as ydl:
            LOGGER.info(f"{self.id}: getting info")
            self._info = ydl.extract_info(self.url, download=False)
            with open(self.info_cache_path(), 'w', encoding="utf-8") as file:
              file.write(json.dumps(ydl.sanitize_info(self._info)))
        except yt_dlp.utils.YoutubeDLError as error:
          raise BadURL(f'Error downloading {repr(self.url)}: {error}')
    return self._info

  def title(self):
    return self.info()['title']

  def raw_metadata(self):
    if self._raw_metadata:
      return self._raw_metadata

    path = self.raw_metadata_cache_path()
    try:
      with open(path, 'r', encoding='utf-8') as file:
        self._raw_metadata = json.load(file)
    except FileNotFoundError:
      self._raw_metadata = ffmpeg.probe(self.raw_video())

      with open(path, 'w', encoding='utf-8') as file:
        json.dump(self._raw_metadata, file)

    return self._raw_metadata

  def get_fps(self):
    metadata = self.raw_metadata()

    for stream in metadata['streams']:
      if stream['codec_type'] == 'video':
        division = stream['avg_frame_rate'].split("/")
        if len(division) == 0:
          continue

        fps = float(division.pop(0))
        for divisor in division:
          fps = fps / float(divisor)

        return fps

    raw_path = self.raw_video()
    raise RuntimeError(f"Could not get FPS for video: {raw_path}")

  def parse_time_spec(self, spec):
    if spec.endswith("F"):
      return "%.3f" % (int(spec[:-1])/self.get_fps())
    else:
      return spec

  def clip(self, start_spec, end_spec):
    if start_spec:
      self.input_options["ss"] = self.parse_time_spec(start_spec)
    if end_spec:
      self.output_options["to"] = self.parse_time_spec(end_spec)
      if start_spec:
        self.output_options["copyts"] = None

  def snapshot(self, time_spec):
    self.input_options["ss"] = self.parse_time_spec(time_spec)
    self.output_options["frames:v"] = "1"
    self.output_options["q:v"] = "2" # JPEG quality
    self._still = True

  def crop(self, crop):
    self._crop = crop

  def overlay_text(self, text):
    self._overlay_text = text

  def audio(self, audio):
    if audio == 'strip':
      self.output_options['an'] = None
    else:
      try:
        del self.output_options['an']
      except KeyError:
        pass

  def video(self, video):
    if video == 'strip':
      self.output_options['vn'] = None
    else:
      try:
        del self.output_options['vn']
      except KeyError:
        pass

  def slow_filter(self, start='0', end=None, amount=2):
    """Set a filter to slow (or speed up) part of the video."""
    if (end is not None and end == start) or amount == 1:
      # Nothing is affected
      self._slow_filter = None
    else:
      self._slow_filter = (start, end, amount)

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

  def raw_video(self):
    path = self.raw_video_cache_path()
    if os.path.exists(path) and os.stat(path).st_size > 0:
      return path

    LOGGER.info(f"{self.id}: downloading raw video to {path}")
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

    return self.output_options

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

    if self._crop is not None:
      parameters.append(f'CROP={repr(self._crop)}')
    if self._overlay_text != '':
      parameters.append(f'OVERLAY_TEXT={repr(self._overlay_text)}')
    if self._slow_filter is not None:
      parameters.append(f'SLOW_FILTER={repr(self._slow_filter)}')

    return parameters

  def processed_video(self):
    output_path = self.processed_video_cache_path()
    if os.path.exists(output_path) and os.stat(output_path).st_size > 0:
      return output_path

    raw_path = self.raw_video()

    parameters = " ".join(self.ffmpeg_parameters())
    LOGGER.info(f"{parameters}: processing video to {output_path}")

    uses_copyts = 'copyts' in self.output_options
    if uses_copyts:
      # -copyts is needed to clip a video to a specific end time, rather than
      # using the desired clip duration. However, it sets the timestamps in the
      # saved video file, which causes a delay before the video starts in
      # certain players (Safari, QuickTime).
      #
      # It’s also incompatible with certain filters, such as concat.
      #
      # To fix this, we reprocess the video, so we want to give it a different
      # name for the first pass.
      first_pass_output_path = self.processed_video_cache_path(prefix='pass1_')
    else:
      first_pass_output_path = output_path

    stream = ffmpeg.input(raw_path, **self.ffmpeg_input_options())

    if "vn" not in self.output_options:
      # Video stream is not being stripped
      if self._crop:
        # FIXME kludge; doesn’t handle named params
        stream = stream.filter('crop', *self._crop.split(':'))

      stream = stream.filter('scale', -2, 500)

      if self._overlay_text:
        stream = stream.drawtext(
          text=self._overlay_text,
          x=20,
          y=20,
          font='Arial',
          fontcolor='white',
          fontsize=48,
          box=1,
          boxcolor='black@0.5',
          boxborderw=20,
        )

      if not uses_copyts:
        # copyts and the concat filter are incompatible
        stream = self._try_apply_slow_filter(stream)

    try:
      (
        stream
        .output(first_pass_output_path, **self.ffmpeg_output_options())
        .overwrite_output()
        .run(quiet=True)
      )
    except ffmpeg.Error as error:
      sys.stderr.buffer.write(error.stderr)
      sys.exit("Error in ffmpeg first pass. See above.")

    if uses_copyts:
      LOGGER.debug(f"{parameters} second pass")

      try:
        stream = ffmpeg.input(first_pass_output_path)
        (
          self._try_apply_slow_filter(stream)
          .output(output_path)
          .overwrite_output()
          .run(quiet=True)
        )
      except ffmpeg.Error as error:
        sys.stderr.buffer.write(error.stderr)
        sys.exit("Error in ffmpeg second pass. See above.")

      os.remove(first_pass_output_path)

    return output_path

  def _try_apply_slow_filter(self, stream):
    if self._slow_filter is None:
      return stream

    (start, end, amount) = self._slow_filter
    if start is None:
      start = '0F'

    split = stream.split()
    parts = []

    if is_non_zero_time(start):
      parts.append(split[len(parts)].trim(start='0', end=start))

    if end is None:
      end_trim = {}
    else:
      end_trim = { 'end': end }

    parts.append(
      split[len(parts)]
      .filter('trim', start=start, **end_trim)
      .setpts(f'{amount}*PTS')
    )

    if end is not None:
      parts.append(split[len(parts)].trim(start=end))

    return ffmpeg.concat(*parts)

  def _try_apply_slow_filter(self, stream):
    if self._slow_filter is None:
      return stream

    (start, end, amount) = self._slow_filter
    if start is None:
      start = '0F'

    split = stream.split()
    parts = []

    if is_non_zero_time(start):
      parts.append(split[len(parts)].trim(start='0', end=start))

    if end is None:
      end_trim = {}
    else:
      end_trim = { 'end': end }

    parts.append(
      split[len(parts)]
      .filter('trim', start=start, **end_trim)
      .setpts(f'{amount}*PTS')
    )

    if end is not None:
      parts.append(split[len(parts)].trim(start=end))

    return ffmpeg.concat(*parts)
