import argparse
import fileinput
import html
from http import server
import functools
import os
import textwrap
import sys

from yanki.anki import DeckParser, CACHE

def cli():
  parser = argparse.ArgumentParser(
    prog='yanki',
    description='Build Anki decks from text files containing YouTube URLs.',
  )
  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('--html', action='store_true',
    help='Produce HTML summary of deck rather than .apkg file.')
  parser.add_argument('--serve-http', action='store_true',
    help='Serve HTML summary of deck on localhost:8000.')
  parser.add_argument('path', nargs='*')
  args = parser.parse_args()

  input = fileinput.input(files=args.path, encoding="utf-8")
  parser = DeckParser(debug=args.verbose)
  decks = parser.parse_input(input)

  if args.serve_http:
    return serve_http(args, decks)

  for deck in decks:
    if args.html:
      print(htmlize_deck(deck, path_prefix=f"{CACHE}/"))
    else:
      deck.save(debug=args.verbose)

  return 0

def serve_http(args, decks):
  deck_links = []

  html_written = set()
  for deck in decks:
    file_name = deck.title.replace('/', '--') + '.html'
    html_path = os.path.join(CACHE, file_name)
    if html_path in html_written:
      raise KeyError(f"Duplicate path after munging deck title: {html_path}")
    html_written.add(html_path)

    with open(html_path, 'w', encoding="utf-8") as file:
      file.write(htmlize_deck(deck, path_prefix=""))

    deck_links.append((file_name, deck))

  # FIXME serve html from memory so that you can run multiple copies of
  # this tool at once.
  with open(os.path.join(CACHE, 'index.html'), 'w', encoding="utf-8") as file:
    file.write(generate_index_html(deck_links))

  # FIXME it would be great to just serve this directory as /static without
  # needing the symlink.
  ensure_static_link()

  print("Starting HTTP server on http://localhost:8000/")
  Handler = functools.partial(server.SimpleHTTPRequestHandler, directory=CACHE)
  try:
    server.HTTPServer(('', 8000), Handler).serve_forever()
  except KeyboardInterrupt:
    return 130

def path_to_web_files():
  from os.path import join, dirname, realpath
  return join(dirname(dirname(realpath(__file__))), 'web-files')

def ensure_static_link():
  web_files_path = path_to_web_files()
  static_path = os.path.join(CACHE, 'static')

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
    # FIXME huge kludge
    # FIXME doesn’t work with images
    path_html = html.escape(note.fields[1].replace("[sound:", path_prefix).removesuffix("]"))
    output += f"""
        <div class="note">
          <h3>{h(note.fields[0])}</h3>
          <video height="300" controls>
            <source src="{path_html}" type="video/mp4">
          </video>
        </div>"""

  return textwrap.dedent(output + f"""
      </body>
    </html>
  """).lstrip()

def h(s):
  return html.escape(s)
