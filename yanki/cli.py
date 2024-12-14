import argparse
import fileinput
import functools
import genanki
import html
from http import server
import logging
import os
from pathlib import PosixPath
import re
import sys
import textwrap

from yanki.anki import DeckParser

LOGGER = logging.getLogger(__name__)

def cli():
  parser = argparse.ArgumentParser(
    prog='yanki',
    description='Build Anki decks from text files containing YouTube URLs.',
  )
  parser.add_argument('-v', '--verbose', action='count', default=0)
  parser.add_argument('--cache',
    default=PosixPath('~/.cache/yanki/').expanduser(),
    help='Path to cache for downloads and media files.')
  parser.add_argument('--html', action='store_true',
    help='Produce HTML summary of deck rather than .apkg file.')
  parser.add_argument('--serve-http', action='store_true',
    help='Serve HTML summary of deck on localhost:8000.')
  parser.add_argument('-o', '--output',
    help=('Path to save decks to. Defaults to saving indivdual decks to their '
      + 'own files named after their sources, but with the extension .apkg.'))
  parser.add_argument('path', nargs='*')
  args = parser.parse_args()

  # Configure logging
  if args.verbose > 2:
    sys.exit('--verbose or -v may only be specified up to 2 times.')
  elif args.verbose == 2:
    level = logging.DEBUG
  elif args.verbose == 1:
    level = logging.INFO
  else:
    level = logging.WARN
  logging.basicConfig(level=level, format='%(message)s')

  os.makedirs(args.cache, exist_ok=True)

  input = fileinput.input(files=args.path, encoding="utf-8")
  parser = DeckParser(cache_path=args.cache)
  decks = parser.parse_input(input)

  if args.serve_http:
    return serve_http(args, decks)

  package = genanki.Package([]) # Only used with --output
  for deck in decks:
    if args.html:
      print(htmlize_deck(deck, path_prefix=args.cache))
    elif args.output == None:
      # Automatically figured out the path to save to.
      deck.save_to_file()
    else:
      deck.save_to_package(package)

  if args.output:
    package.write_to_file(args.output)
    LOGGER.info(f"Wrote decks to file {args.output}")

  return 0

def serve_http(args, decks):
  deck_links = []

  html_written = set()
  for deck in decks:
    file_name = deck.title.replace('/', '--') + '.html'
    html_path = os.path.join(args.cache, file_name)
    if html_path in html_written:
      raise KeyError(f"Duplicate path after munging deck title: {html_path}")
    html_written.add(html_path)

    with open(html_path, 'w', encoding="utf-8") as file:
      file.write(htmlize_deck(deck, path_prefix=""))

    deck_links.append((file_name, deck))

  # FIXME serve html from memory so that you can run multiple copies of
  # this tool at once.
  index_path = os.path.join(args.cache, 'index.html')
  with open(index_path, 'w', encoding="utf-8") as file:
    file.write(generate_index_html(deck_links))

  # FIXME it would be great to just serve this directory as /static without
  # needing the symlink.
  ensure_static_link(args.cache)

  print("Starting HTTP server on http://localhost:8000/")
  Handler = functools.partial(
    server.SimpleHTTPRequestHandler,
    directory=args.cache)
  try:
    server.HTTPServer(('', 8000), Handler).serve_forever()
  except KeyboardInterrupt:
    return 130

def path_to_web_files():
  from os.path import join, dirname, realpath
  return join(dirname(dirname(realpath(__file__))), 'web-files')

def ensure_static_link(cache_path):
  web_files_path = path_to_web_files()
  static_path = os.path.join(cache_path, 'static')

  try:
    os.symlink(web_files_path, static_path)
  except FileExistsError as e:
    if os.readlink(static_path) == web_files_path:
      # Symlink already exists
      return

  try:
    os.remove(static_path)
  except Exception as e:
    sys.exit(f"Error removing {static_path} replace with symlink: {e}")

  try:
    os.symlink(web_files_path, static_path)
  except Exception as e:
    sys.exit(f"Error symlinking {static_path} to {web_files_path}: {e}")

def static_url(path):
  mtime = os.path.getmtime(os.path.join(path_to_web_files(), path))
  return f"/static/{path}?{mtime}"

def generate_index_html(deck_links):
  output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>Decks</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url('general.css')}">
      </head>
      <body>
        <h1>Decks</h1>

        <ol>
  """

  for (file_name, deck) in deck_links:
    output += f"""
          <li><a href="{h(file_name)}">{h(deck.title)}</a></li>"""

  return textwrap.dedent(output + f"""
        </ol>
      </body>
    </html>
  """).lstrip()

def htmlize_deck(deck, path_prefix=""):
  output = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <title>{h(deck.title)}</title>
        <meta charset="utf-8">
        <link rel="stylesheet" href="{static_url('general.css')}">
      </head>
      <body>
        <h1>{h(deck.title)}</h1>
  """

  for note in deck.notes.values():
    output += f"""
        <div class="note">
          <h3>{note.fields[0].render_html(path_prefix)}</h3>
          {note.fields[1].render_html(path_prefix)}
          <p class="note_id">{h(note.note_id)}</p>
        </div>"""

  return textwrap.dedent(output + f"""
      </body>
    </html>
  """).lstrip()

def h(s):
  return html.escape(s)
