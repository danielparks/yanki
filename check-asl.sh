#!/bin/sh

result=0

# FIXME this should really be built into yanki
output=$(yanki list-notes -f '{note_id}' asl/*.deck | sort | uniq -d)
if [[ ! -z "$output" ]] ; then
  echo 'Found duplicate note:'
  echo
  echo $output
  result=1
fi

output=$(
  yanki list-notes -f '{url} {source_path} {line_number}' asl/*.deck \
  | grep '^http.*lifeprint.*\.htm'
)
if [[ ! -z "$output" ]] ; then
  if [[ $result = 1 ]] ; then echo ; fi
  echo 'Found note with Lifeprint page URL:'
  echo
  echo $output
  result=1
fi

output=$(
  grep '^  more:.*lifeprint.com' asl/extra-full-pages.deck | sort --check 2>&1
)
if [[ ! -z "$output" ]] ; then
  if [[ $result = 1 ]] ; then echo ; fi
  echo 'asl/extra-full-pages.deck not sorted:'
  echo $output
  result=1
fi

output=$(
  yanki list-notes -f '{text}' asl/extra-miscellaneous.deck | sort --check 2>&1
)
if [[ ! -z "$output" ]] ; then
  if [[ $result = 1 ]] ; then echo ; fi
  echo 'asl/extra-miscellaneous.deck not sorted:'
  echo $output
  result=1
fi

exit $result
