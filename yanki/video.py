import ffmpeg
import hashlib
import json
import logging
import os
import shlex
import shutil
import sys
from urllib.parse import urlparse, parse_qs
import yt_dlp

LOGGER = logging.getLogger(__name__)

YT_DLP_OPTIONS = {
  'quiet': True,
  'skip_unavailable_fragments': False,
}

STILL_FORMATS = frozenset(['png', 'jpeg', 'jpg'])

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
  url = urlparse(url_str)
  query = parse_qs(url.query)

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

def file_url_to_path(url):
  parts = urlparse(url)
  if parts.scheme.lower() != 'file':
    return None

  # urlparse doesn’t handle file: very well:
  #
  #   >>> urlparse('file://./media/first.png')
  #   ParseResult(scheme='file', netloc='.', path='/media/first.png', ...)
  return parts.netloc + parts.path

def file_not_empty(path):
  """Checks that the path is a file and is non-empty."""
  return os.path.exists(path) and os.stat(path).st_size > 0

NON_ZERO_DIGITS = set('123456789')
def is_non_zero_time(time_spec):
  for c in time_spec:
    if c in NON_ZERO_DIGITS:
      return True
  return False

def get_key_path(data, path: list[any]):
  for key in path:
    data = data[key]
  return data

# FIXME cannot be reused
class Video:
  def __init__(self, url, working_dir='.', cache_path='.', reprocess=False):
    self.url = url
    self.working_dir = working_dir
    self.cache_path = cache_path
    self.reprocess = reprocess
    self._info = None
    self._raw_metadata = None
    self._format = None

    # ffmpeg parameters. Every run with the same parameters should produce the
    # same video (assuming the source hasn’t changed).
    self.id = url_to_id(url)
    if '/' in self.id:
      raise BadURL(f"Invalid '/' in video ID: {repr(self.id)}")
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
    return self.cached(f'{prefix}{parameters}.{self.output_ext()}')

  def _download_info(self):
    path = file_url_to_path(self.url)
    if path is not None:
      return {
        'title': os.path.splitext(os.path.basename(path))[0],
        'ext': os.path.splitext(path)[1][1:],
      }

    try:
      with yt_dlp.YoutubeDL(YT_DLP_OPTIONS.copy()) as ydl:
        LOGGER.info(f'{self.id}: getting info')
        return ydl.sanitize_info(ydl.extract_info(self.url, download=False))
    except yt_dlp.utils.YoutubeDLError as error:
      raise BadURL(f'Error downloading {repr(self.url)}: {error}')

  def info(self):
    if self._info:
      return self._info

    try:
      with open(self.info_cache_path(), 'r', encoding='utf-8') as file:
        self._info = json.load(file)
        return self._info
    except FileNotFoundError:
      # Either the file wasn’t found, wasn’t valid JSON, or it didn’t have the
      # key path. We use `pass` here to avoid adding this exception to the
      # context of new exceptions.
      pass

    self._info = self._download_info()
    with open(self.info_cache_path(), 'w', encoding='utf-8') as file:
      file.write(json.dumps(self._info))
    return self._info

  def title(self):
    return self.info()['title']

  def refresh_raw_metadata(self):
    LOGGER.debug(f'refresh raw metadata: {self.raw_video()}')
    self._raw_metadata = ffmpeg.probe(self.raw_video())

    with open(self.raw_metadata_cache_path(), 'w', encoding='utf-8') as file:
      json.dump(self._raw_metadata, file)

    return self._raw_metadata

  # This will refresh metadata once if it doesn’t find the passed path the
  # first time.
  def raw_metadata(self, *path):
    try:
      # FIXME? Track if ffprobe was already run and don’t run it again.
      if self._raw_metadata:
        return get_key_path(self._raw_metadata, path)

      with open(self.raw_metadata_cache_path(), 'r', encoding='utf-8') as file:
        self._raw_metadata = json.load(file)
        return get_key_path(self._raw_metadata, path)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
      # Either the file wasn’t found, wasn’t valid JSON, or it didn’t have the
      # key path. We use `pass` here to avoid adding this exception to the
      # context of new exceptions.
      pass

    return get_key_path(self.refresh_raw_metadata(), path)

  def get_fps(self):
    for stream in self.raw_metadata('streams'):
      if stream['codec_type'] == 'video':
        division = stream['avg_frame_rate'].split('/')
        if len(division) == 0:
          continue

        fps = float(division.pop(0))
        for divisor in division:
          fps = fps / float(divisor)

        return fps

    raise RuntimeError(f'Could not get FPS for video: {self.raw_video()}')

  def normalize_time_spec(self, spec):
    if spec.endswith('F'):
      return '%.3f' % (int(spec[:-1])/self.get_fps())
    else:
      return spec

  def clip(self, start_spec, end_spec):
    if start_spec:
      self.input_options['ss'] = self.normalize_time_spec(start_spec)
    if end_spec:
      self.output_options['to'] = self.normalize_time_spec(end_spec)
      if start_spec:
        self.output_options['copyts'] = None

  def snapshot(self, time_spec):
    self.input_options['ss'] = self.normalize_time_spec(time_spec)
    self.output_options['frames:v'] = '1'
    self.output_options['q:v'] = '2' # JPEG quality

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

  def format(self, extension: str | None):
    if extension is None:
      self._format = None
    else:
      self._format = extension.lower()

  def output_ext(self):
    if self._format is not None:
      return self._format
    elif self.is_still():
      return 'jpeg'
    else:
      return 'mp4'

  def is_still(self):
    return (
      str(self.output_options.get('frames:v')) == '1'
      or self._format in STILL_FORMATS
      or 'duration' not in self.raw_metadata('format')
    )

  def raw_video(self):
    path = self.raw_video_cache_path()
    if os.path.exists(path) and os.stat(path).st_size > 0:
      return path

    LOGGER.info(f'{self.id}: downloading raw video to {path}')

    # Check if it’s a file:// URL
    source_path = file_url_to_path(self.url)
    if source_path is not None:
      source_path = os.path.join(self.working_dir, source_path)
      shutil.copy(source_path, path, follow_symlinks=True)
      return path

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
    if 'vf' in self.output_options:
      # FIXME?
      raise ValueError('vf output option already set')

    return self.output_options

  def ffmpeg_parameters(self):
    """
    Get most parameters to ffmpeg. Used to identify output for caching.

    Does not include input or output file names, or options like -y.
    """
    parameters = []

    for key, value in self.ffmpeg_input_options().items():
      parameters.append(f'-{key}')
      if value is not None:
        parameters.append(value)

    parameters.append(self.id)

    for key, value in self.ffmpeg_output_options().items():
      parameters.append(f'-{key}')
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
    if not self.reprocess and file_not_empty(output_path):
      return output_path

    # Only reprocess once per run.
    self.reprocess = False

    raw_path = self.raw_video()

    parameters = ' '.join(self.ffmpeg_parameters())
    LOGGER.info(f'{parameters}: processing video to {output_path}')

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

    if 'vn' not in self.output_options:
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

    stream = (
      stream
      .output(first_pass_output_path, **self.ffmpeg_output_options())
      .overwrite_output()
    )

    if uses_copyts:
      verb = 'First pass'
    else:
      verb = 'Run'

    command = shlex.join(stream.compile())
    LOGGER.debug(f'{verb} {command}')
    try:
      stream.run(quiet=True)
    except ffmpeg.Error as error:
      error.add_note(f'{verb}: {command}')
      raise

    if uses_copyts:
      stream = ffmpeg.input(first_pass_output_path)
      stream = (
        self._try_apply_slow_filter(stream)
        .output(output_path)
        .overwrite_output()
      )

      command = shlex.join(stream.compile())
      LOGGER.debug(f'Second pass: {command}')
      try:
        stream.run(quiet=True)
      except ffmpeg.Error as error:
        error.add_note(f'Second pass: {command}')
        raise

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
