# Change log

All notable changes to this project will be documented in this file.

## Release 0.6.0 (2025-08-16)

* Added flashcard web UI so that decks can be used without Anki.
* Added experimental automatic video trimming with `trim: auto`.
* Fixed a few race conditions; in particular slicing up a long video into many
  flashcards now avoids a condition that could cause significant slow-downs.
* Cleaned up CLI commands.
