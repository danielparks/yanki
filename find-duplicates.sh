#!/bin/sh

set -e

# FIXME this should really be built into yanki
output=$(yanki list-notes -f '{note_id}' "$@" | sort | uniq -d)
if [[ ! -z "$output" ]] ; then
  echo $output
  exit 1
fi
