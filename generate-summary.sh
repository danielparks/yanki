#!/bin/sh

set -e

yanki list-notes -f '{note_id} TEXT: {text!r}
{note_id} TAGS: {tags!r}
{note_id} MORE: {more!r}' asl/*.deck \
| sort \
>asl/summary.txt

git --no-pager diff --word-diff-regex=. -U1 --color=always asl/summary.txt
