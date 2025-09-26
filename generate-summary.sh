#!/bin/sh

set -e -o pipefail

cache_prefix=${YANKI_CACHE:-$HOME/.cache/yanki/}
temp_out=$(mktemp)

yanki list-notes -f '{note_id} MEDIA: {media_paths!r}
{note_id} MORE: {more!r}
{note_id} PARAMETERS: {video_parameters}
{note_id} TAGS: {tags!r}
{note_id} TEXT: {text!r}' asl/*.deck \
| sed -e "/ MEDIA: /s#${cache_prefix}##g" \
| awk '
  # Split PARAMETERS: into multiple PARAMETER: lines.
  / PARAMETERS: / {
    split($0, parts, " PARAMETERS:");
    prefix=parts[1]" PARAMETER:";
    gsub(/\n/, "", parts[2]);
    gsub(/ [a-z_]+=/, "\n"prefix"&", parts[2]);
    gsub(/^\n/, "", parts[2]);
    print(parts[2]);
    next;
  }
  // { print }' \
| LC_COLLATE=C sort \
>"$temp_out"

# Update all at once so that yanki failing, or killing script this in the middle
# of a run doesn’t produce an empty file.
mv "$temp_out" asl/summary.txt

git --no-pager diff --no-ext-diff --word-diff-regex=. -U1 --color=always asl/summary.txt
