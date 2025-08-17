# Change log

All notable changes to this project will be documented in this file.

## main branch

### Minor changes

* Update README.md and project description now that flashcards can be used directlty (through the web UI) rather than requiring Anki.

## Release 0.6.0 (2025-08-16)

* Added flashcard web UI so that decks can be used without Anki.
* Added experimental automatic video trimming with `trim: auto`.
* Fixed a few race conditions; in particular slicing up a long video into many flashcards now avoids a condition that could cause significant slow-downs.
* Cleaned up CLI commands.
