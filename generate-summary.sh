#!/bin/sh

set -e

yanki list-notes -f '{note_id} MEDIA: {media_paths!r}
{note_id} MORE: {more!r}
{note_id} TAGS: {tags!r}
{note_id} TEXT: {text!r}' asl/*.deck \
| sort \
>asl/summary.txt

git --no-pager diff --word-diff-regex=. -U1 --color=always asl/summary.txt
