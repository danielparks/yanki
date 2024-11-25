import argparse
import fileinput
import html
import textwrap

from yanki.anki import DeckParser

def cli():
  parser = argparse.ArgumentParser(
    prog='yanki',
    description='Builds an Anki deck from a text file containing YouTube URLs.',
  )
  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('--html', action='store_true',
    help='Produce HTML summary of deck rather than .apkg file.')
  parser.add_argument('path', nargs='*')
  args = parser.parse_args()

  input = fileinput.input(files=args.path, encoding="utf-8")
  parser = DeckParser(debug=args.verbose)
  for deck in parser.parse_input(input):
    if args.html:
      htmlize_deck(deck)
    else:
      deck.save(debug=args.verbose)

  return 0

def htmlize_deck(deck):
  title_html = html.escape(deck.title)
  print(textwrap.dedent(f"""
    <!DOCTYPE html>
    <html>
      <head>
      <title>{title_html}</title>
      </head>
      <body>
        <h1>{title_html}</h1>
  """))
  for note in deck.notes.values():
    question_html = html.escape(note.fields[0])
    # FIXME huge kludge
    path_html = html.escape(note.fields[1].replace("[sound:", "cache/").removesuffix("]"))
    print(f"""
      <div class="note">
        <h3>{question_html}</h3>
        <video height="300" controls>
          <source src="{path_html}" type="video/mp4">
        </video>
      </div>""")
  print(textwrap.dedent(f"""
      </body>
    </html>
  """))
