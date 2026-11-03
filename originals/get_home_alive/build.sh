#!/bin/sh
# Build get_home_alive.z5 from get_home_alive.inf with the Inform 6 compiler
# (Homebrew: brew install inform6).
cd "$(dirname "$0")"
INFORM=/opt/homebrew/opt/inform6/bin/inform
LIB=/opt/homebrew/opt/inform6/share/inform/std/lib
"$INFORM" -v5 +include_path="$LIB" get_home_alive.inf
