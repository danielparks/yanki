#!/bin/sh

set -e

cache_prefix=${YANKI_CACHE:-$HOME/.cache/yanki/}

yanki list-notes -f '{note_id} MEDIA: {media_paths!r}
{note_id} MORE: {more!r}
{note_id} TAGS: {tags!r}
{note_id} TEXT: {text!r}' asl/*.deck \
| sed -e "/ MEDIA: /s#${cache_prefix}##g" \
| LC_COLLATE=C sort \
>asl/summary.txt

git --no-pager diff --no-ext-diff --word-diff-regex=. -U1 --color=always asl/summary.txt
