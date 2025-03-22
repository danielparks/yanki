#!/bin/sh

set -e

# FIXME this should really be built into yanki
yanki list-notes -f '{note_id}' "$@" | sort | uniq -d
