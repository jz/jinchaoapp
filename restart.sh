#!/usr/bin/env sh
# restart.sh — Stop then start the web Go server.
# Usage: sh restart.sh        (restart in foreground)
#        sh restart.sh -d     (restart in background)

set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"

sh "$DIR/stop.sh"
sleep 1
exec sh "$DIR/start.sh" "$@"
