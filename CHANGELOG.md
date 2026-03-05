# Change log

All notable changes to this project will be documented in this file.

## Release 0.6.1 (2026-03-05)

### Security

* Updated [yt-dlp] dependency to require version 2026.2.21 or newer. Previous versions had a vulnerability in `netrc_cmd` handling ([GHSA-g3gw-q23r-pgqm], [CVE-2026-26331]). Yanki does not use `netrc`, and thus was not affected, but I upgraded out of an abundance of caution.

[yt-dlp]: https://github.com/yt-dlp/yt-dlp
[GHSA-g3gw-q23r-pgqm]: https://github.com/advisories/GHSA-g3gw-q23r-pgqm
[CVE-2026-26331]: https://nvd.nist.gov/vuln/detail/CVE-2026-26331

### Minor changes

* Update README.md and project description now that flashcards can be used directly (through the web UI) rather than requiring Anki.

## Release 0.6.0 (2025-08-16)

* Added flashcard web UI so that decks can be used without Anki.
* Added experimental automatic video trimming with `trim: auto`.
* Fixed a few race conditions; in particular slicing up a long video into many flashcards now avoids a condition that could cause significant slow-downs.
* Cleaned up CLI commands.
