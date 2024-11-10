from ffmpeg import FFmpeg
import yt_dlp
import json
import os
import urllib

CACHE = './cache'
YT_DLP_OPTIONS = {
  'quiet': True,
  'skip_unavailable_fragments': False,
}

os.makedirs(CACHE, exist_ok=True)

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

class Video:
  def __init__(self, url):
    self.url = url
    self.id = yt_url_to_id(url)
    self._info = None

  def info_cache_path(self):
    return os.path.join(CACHE, self.id + '_info.json')

  def raw_video_cache_path(self, logger=LOGGER):
    return os.path.join(CACHE, self.id + '_raw.' + self.info(logger=logger)['ext'])

  def processed_video_cache_path(self):
    return os.path.join(CACHE, self.id + '_processed.mp4')

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

    logger.info(f"{self.id}: processing video")
    FFmpeg().option("y").input(raw_path).output(
      output_path,
      vf="crop=in_h:in_h,scale=500:500",
      an=None,
    ).execute()

    return output_path

if __name__ == '__main__':
  import fileinput
  for url in fileinput.input(encoding="utf-8"):
    video = Video(url)
    print(video.processed_video())
