import ffmpeg
import hashlib
import json
import logging
import math
import os
from os.path import getmtime
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
TIME_FORMAT = '%0.6f'
FILENAME_ILLEGAL_CHARS = '/"[]'

def chars_in(chars, input):
  return [char for char in chars if char in input]

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

  # FIXME check this against FILENAME_ILLEGAL_CHARS somehow
  return (
    url_str
    .replace('\\', '\\\\')
    .replace('|', r'\|')
    .replace('"', r"\'")
    .replace('[', r"\(")
    .replace(']', r"\)")
    .replace('/', '|')
  )

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

def get_key_path(data, path: list[any]):
  for key in path:
    data = data[key]
  return data

# FIXME cannot be reused
class Video:
  def __init__(self, url, working_dir='.', cache_path='.', reprocess=False, logger=LOGGER):
    self.url = url
    self.working_dir = working_dir
    self.cache_path = cache_path
    self.reprocess = reprocess
    self.logger = logger

    self.id = url_to_id(url)
    invalid = chars_in(FILENAME_ILLEGAL_CHARS, self.id)
    if invalid:
      raise BadURL(
        f'Invalid characters ({"".join(invalid)}) in video ID: {repr(self.id)}'
      )

    self._info = None
    self._raw_metadata = None
    self._format = None
    self._crop = None
    self._overlay_text = ''
    self._slow_filter = None
    self.input_options = {}
    self.output_options = {}
    self._parameters = {}

  def cached(self, filename):
    return os.path.join(self.cache_path, filename)

  def info_cache_path(self):
    return self.cached(f'info_{self.id}.json')

  def raw_video_cache_path(self):
    return self.cached('raw_' + self.id + '.' + self.info()['ext'])

  def raw_metadata_cache_path(self):
    return self.cached(f'ffprobe_raw_{self.id}.json')

  def processed_video_cache_path(self, prefix='processed_'):
    parameters = '_'.join(self.parameters())

    if len(parameters) > 60 or chars_in(FILENAME_ILLEGAL_CHARS, parameters):
      parameters = hashlib.blake2b(
        parameters.encode(encoding='utf-8'),
        digest_size=16,
        usedforsecurity=False).hexdigest()
    return self.cached(f'{prefix}{self.id}_{parameters}.{self.output_ext()}')

  def _download_info(self):
    path = file_url_to_path(self.url)
    if path is not None:
      return {
        'title': os.path.splitext(os.path.basename(path))[0],
        'ext': os.path.splitext(path)[1][1:],
      }

    try:
      with yt_dlp.YoutubeDL(YT_DLP_OPTIONS.copy()) as ydl:
        self.logger.info(f'getting info')
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
    self.logger.debug(f'refresh raw metadata: {self.raw_video()}')
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

      metadata_cache_path = self.raw_metadata_cache_path()
      if getmtime(metadata_cache_path) >= getmtime(self.raw_video()):
        # Metadata isn’t older than raw video.
        with open(metadata_cache_path, 'r', encoding='utf-8') as file:
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

  # Expects spec without whitespace
  def time_to_seconds(self, spec):
    """Converts a time spec like 1:01.02 or 4F to decimal seconds."""
    if isinstance(spec, float) or isinstance(spec, int):
      return float(spec)

    if spec.endswith('F') or spec.endswith('f'):
      # Frame number
      return int(spec[:-1])/self.get_fps()

    # FIXME handle s/ms/us suffixes

    # [-][HH]:[MM]:[SS.mmm...]
    sign = 1
    if spec.startswith('-'):
      spec = spec[1:]
      sign = -1

    # FIXME? this acccepts 3.3:500:67.8:0:1.2
    sum = 0
    for part in spec.split(':'):
      sum = sum*60 + float(part)

    return sign*sum

  def time_to_seconds_str(self, spec, format=TIME_FORMAT):
    """
    Converts a time spec like 1:01.02 or 4F to decimal seconds as a string.

    Handles spec being '' or None by returning '' in those cases.
    """
    if spec is None or spec == '':
      return ''
    else:
      return format % self.time_to_seconds(spec)

  def clip(self, start_spec, end_spec):
    if start_spec:
      start = self.time_to_seconds(start_spec)
      self.input_options['ss'] = TIME_FORMAT % start
    else:
      start = 0

    if end_spec:
      end = self.time_to_seconds(end_spec)
      self.input_options['t'] = TIME_FORMAT % (end - start)
      self._parameters['clip'] = (start, end)
    else:
      self._parameters['clip'] = (start, None)

    if 'snapshot' in self._parameters:
      del self._parameters['snapshot']

  def snapshot(self, time_spec):
    self.input_options['ss'] = self.time_to_seconds_str(time_spec)
    self.output_options['frames:v'] = '1'
    self.output_options['q:v'] = '2' # JPEG quality

    self._parameters['snapshot'] = self.input_options['ss']
    if 'clip' in self._parameters:
      del self._parameters['clip']

  def crop(self, crop):
    self._crop = crop

  def overlay_text(self, text):
    self._overlay_text = text

  def audio(self, audio):
    if audio == 'strip':
      self.output_options['an'] = None
      self._parameters['audio'] = 'strip'
    else:
      if 'an' in self.output_options:
        del self.output_options['an']
      if 'audio' in self._parameters:
        del self._parameters['audio']

  def video(self, video):
    if video == 'strip':
      self.output_options['vn'] = None
      self._parameters['video'] = 'strip'
    else:
      if 'vn' in self.output_options:
        del self.output_options['vn']
      if 'video' in self._parameters:
        del self._parameters['video']

  def slow_filter(self, start=0, end=None, amount=2):
    """Set a filter to slow (or speed up) part of the video."""
    if start == '' or start is None:
      start = 0
    else:
      start = self.time_to_seconds(start)

    if end == '' or end is None:
      end = None
    else:
      end = self.time_to_seconds(end)

    if (end is not None and end == start) or amount == 1:
      # Nothing is affected
      self._slow_filter = None
    else:
      self._slow_filter = (start, end, float(amount))

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

  def has_audio(self):
    """Does the raw video contain an audio stream?"""
    for stream in self.raw_metadata('streams'):
      if stream['codec_type'] == 'audio':
        return True
    return False

  def wants_audio(self):
    """Should the output include an audio stream?"""
    return (
      'an' not in self.output_options
      and self.has_audio()
      and not self.is_still()
    )

  def has_video(self):
    """Does the raw video contain a video stream or image?"""
    for stream in self.raw_metadata('streams'):
      if stream['codec_type'] == 'video':
        return True
    return False

  def wants_video(self):
    """Should the output include a video stream or image?"""
    return (
      'vn' not in self.output_options
      and self.has_video()
    )

  def raw_video(self):
    path = self.raw_video_cache_path()
    path_exists = os.path.exists(path) and os.stat(path).st_size > 0

    # Check if it’s a file:// URL
    source_path = file_url_to_path(self.url)
    if source_path is not None:
      source_path = os.path.join(self.working_dir, source_path)
      if not path_exists or getmtime(source_path) > getmtime(path):
        # Cache file doesn’t exist or is old.
        self.logger.info(f'downloading raw video to {path}')
        shutil.copy(source_path, path, follow_symlinks=True)
      return path

    if path_exists:
      # Already cached, and we can’t check if it’s out of date.
      return path

    self.logger.info(f'downloading raw video to {path}')

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

  def parameters(self):
    """Get parameters for producing the video."""
    parameters = [
      f'{key}={repr(value)}'
      for key, value in self._parameters.items()
    ]

    if self._crop is not None:
      parameters.append(f'crop={repr(self._crop)}')
    if self._overlay_text != '':
      parameters.append(f'overlay_text={repr(self._overlay_text)}')
    if self._slow_filter is not None:
      parameters.append(f'slow={repr(self._slow_filter)}')

    return parameters

  def processed_video(self):
    output_path = self.processed_video_cache_path()
    if not self.reprocess and file_not_empty(output_path):
      return output_path

    # Only reprocess once per run.
    self.reprocess = False

    parameters = ' '.join(self.parameters())
    self.logger.info(f'processing with ({parameters}) to {output_path}')

    stream = ffmpeg.input(self.raw_video(), **self.ffmpeg_input_options())
    output_streams = dict()

    if self.wants_video():
      # Video stream is not being stripped
      video = stream['v']
      if self._crop:
        # FIXME kludge; doesn’t handle named params
        video = video.filter('crop', *self._crop.split(':'))

      video = video.filter('scale', -2, 500)

      if self._overlay_text:
        video = video.drawtext(
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

      output_streams['v'] = video

    if self.wants_audio():
      # Audio stream is not being stripped
      audio = stream['a']
      output_streams['a'] = audio

    output_streams = self._try_apply_slow_filter(output_streams)
    if isinstance(output_streams, dict):
      output_streams = output_streams.values()
    else:
      output_streams = [output_streams]

    stream = ffmpeg.output(
      *output_streams,
      output_path,
      **self.ffmpeg_output_options()
    ).overwrite_output()

    command = shlex.join(stream.compile())
    self.logger.debug(f'Run {command}')
    try:
      stream.run(quiet=True)
    except ffmpeg.Error as error:
      error.add_note(f'Ran: {command}')
      raise

    return output_path

  # Expect { 'v': video?, 'a' : audio? } depending on if -vn and -an are set.
  def _try_apply_slow_filter(self, streams):
    if self._slow_filter is None:
      return streams

    # These are already floats (or None for end):
    (start, end, amount) = self._slow_filter

    wants_video = self.wants_video()
    wants_audio = self.wants_audio()
    parts = []
    i = 0

    if wants_video:
      vsplit = streams['v'].split()
    if wants_audio:
      asplit = streams['a'].asplit()

    if start != 0:
      if wants_video:
        parts.append(
          vsplit[i]
          .filter('select', f'between(t,0,{start})')
          .filter('setpts', 'PTS-STARTPTS')
        )
      if wants_audio:
        parts.append(
          asplit[i]
          .filter('aselect', f'between(t,0,{start})')
          .filter('asetpts', 'PTS-STARTPTS')
        )
      i += 1

    if end is None:
      expression = f'gte(t,{start})'
    else:
      expression = f'between(t,{start},{end})'

    if wants_video:
      parts.append(
        vsplit[i]
        .filter('select', expression)
        .filter('setpts', 'PTS-STARTPTS')
        .setpts(f'{amount}*PTS')
      )
    if wants_audio:
      part = (
        asplit[i]
        .filter('aselect', expression)
        .filter('asetpts', 'PTS-STARTPTS')
      )

      if amount < 0.01:
        # FIXME validate on parse
        raise ValueError('Cannot slow audio by less than 0.01')
      elif amount > 2:
        twos_count = math.floor(math.log2(amount))
        for _ in range(twos_count):
          part = part.filter('atempo', 0.5)
        last_amount = amount/2**twos_count
        if last_amount != 1:
          part = part.filter('atempo', 1/last_amount)
      else:
        part = part.filter('atempo', 1/amount)

      parts.append(part)
    i += 1

    if end is not None:
      if wants_video:
        parts.append(
          vsplit[i]
          .filter('select', f'gte(t,{end})')
          .filter('setpts', 'PTS-STARTPTS')
        )
      if wants_audio:
        parts.append(
          asplit[i]
          .filter('aselect', f'gte(t,{end})')
          .filter('asetpts', 'PTS-STARTPTS')
        )

    return ffmpeg.concat(*parts, v=int(wants_video), a=int(wants_audio))
