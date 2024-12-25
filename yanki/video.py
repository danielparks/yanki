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
    self.id = url_to_id(url)
    if '/' in self.id:
      raise BadURL(f'Invalid "/" in video ID: {repr(self.id)}')
    self._info = None
    self._raw_metadata = None
    self._crop = None
    self._overlay_text = ''
    self._format = None
    self._still = False
    self.input_options = {}
    self.output_options = {}
    self.filter_complex = None

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
    if self.filter_complex:
      parameters += '/' + self.filter_complex

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
      with open(path, 'r', encoding="utf-8") as file:
        self._raw_metadata = json.load(file)
    except FileNotFoundError:
      metadata_json = ffmpeg.FFmpeg(executable="ffprobe").input(
          self.raw_video(),
          print_format="json",
          show_streams=None,
        ).execute()
      self._raw_metadata = json.loads(metadata_json)

      with open(path, 'wb') as file:
        file.write(metadata_json)

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
      self.filter_complex = None
      return

    start = start.replace(':', '\\\\:')
    pieces = []
    if is_non_zero_time(start):
      i = len(pieces)
      pieces.append(f'[0]trim=0:{start}[v{i}]')

    # The piece that is slowed
    if end is not None:
      end = end.replace(':', '\\\\:')
      trim = f'{start}:{end}'
    else:
      trim = f'{start}'

    i = len(pieces)
    pieces.append(
      f'[0]trim={trim}[v{i}];'
      + f'[v{i}]setpts={amount}*PTS[v{i}]'
    )

    if end is not None:
      i = len(pieces)
      pieces.append(f'[0]trim={end}[v{i}]')

    # Concatenate all the pieces together
    inputs = "".join([f'[v{i}]' for i in range(len(pieces))])
    pieces.append(f'{inputs}concat=n={len(pieces)}')

    self.filter_complex = ';'.join(pieces)

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

    if "vn" in self.output_options:
      # video: strip mode, don’t use -vf
      return self.output_options

    vf = []
    if self._crop:
      vf.append(f"crop={self._crop}")
    if self._overlay_text:
      # FIXME escaping https://superuser.com/questions/1821926/how-to-escape-file-path-for-burned-in-text-based-subtitles-with-ffmpeg/1822055#1822055
      vf.append(f"drawtext=text='{self._overlay_text}':x=20:y=20:font=Arial"
        ":fontcolor=white:fontsize=48:box=1:boxcolor=black@0.5:boxborderw=20")
    vf.append("scale=-2:500")

    return {
      "vf": ",".join(vf),
      **self.output_options,
    }

  def ffmpeg_parameters(self):
    """
    Get most parameters to ffmpeg. Used to identify output for caching.

    Does not include input or output file names, or options like -y.

    Does not include -filter_complex, since it runs in a second pass.
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

  def processed_video(self):
    output_path = self.processed_video_cache_path()
    if os.path.exists(output_path) and os.stat(output_path).st_size > 0:
      return output_path

    raw_path = self.raw_video()

    parameters = " ".join(self.ffmpeg_parameters())
    LOGGER.info(f"{parameters}: processing video to {output_path}")

    second_pass = self.filter_complex or 'copyts' in self.output_options
    if second_pass:
      # -filter_complex is incompatible with -vf, so we do it in a second pass.
      #
      # -copyts is needed to clip a video to a specific end time, rather than
      # using the desired clip duration. However, it sets the timestamps in the
      # saved video file, which causes a delay before the video starts in
      # certain players (Safari, QuickTime).
      #
      # To fix this, we reprocess the video, so we want to give it a different
      # name for the first pass.
      first_pass_output_path = self.processed_video_cache_path(prefix='pass1_')
    else:
      first_pass_output_path = output_path

    try:
      ffmpeg.FFmpeg() \
        .option("y") \
        .input(raw_path, self.ffmpeg_input_options()) \
        .output(first_pass_output_path, self.ffmpeg_output_options()) \
        .execute()
    except ffmpeg.errors.FFmpegError as error:
      sys.exit(f"""ffmpeg: {error}
        input: {raw_path}
        {self.ffmpeg_input_options()}
        output: {first_pass_output_path}
        {self.ffmpeg_output_options()}""".replace("\n      ", "\n"))

    if second_pass:
      if self.filter_complex:
        LOGGER.debug(f"{parameters} second pass: running filter_complex {self.filter_complex}")
      else:
        LOGGER.debug(f"{parameters} second pass: (no filter)")

      command = ffmpeg.FFmpeg().option("y")
      if self.filter_complex:
        command.option('filter_complex', self.filter_complex)
      try:
        command.input(first_pass_output_path).output(output_path).execute()
      except ffmpeg.errors.FFmpegError as error:
        sys.exit(f"""ffmpeg: {error}
          filter_complex: {self.filter_complex}
          input: {first_pass_output_path}
          output: {output_path}""".replace("\n        ", "\n"))

      os.remove(first_pass_output_path)

    return output_path
