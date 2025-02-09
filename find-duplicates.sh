#!/bin/sh

set -e

# FIXME this should really buit in to yanki
yanki list-notes -f '{note_id}' "$@" | sort | uniq -d
