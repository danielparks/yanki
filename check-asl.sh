#!/bin/sh

set -e -o pipefail

result=0

# FIXME this should really be built into yanki
output=$(yanki list-notes -f '{note_id}' "$@" | sort | uniq -d)
if [[ ! -z "$output" ]] ; then
  echo 'Found duplicate note:'
  echo
  echo $output
  result=1
fi

output=$(
  yanki list-notes -f '{url} {source_path} {line_number}' "$@" \
  | grep '^http.*lifeprint.*\.htm'
)
if [[ ! -z "$output" ]] ; then
  if [[ $result = 1 ]] ; then echo ; fi
  echo 'Found note with Lifeprint page URL:'
  echo
  echo $output
  result=1
fi
