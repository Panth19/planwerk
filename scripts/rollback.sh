#!/usr/bin/env bash
# Roll back to the previously deployed version, or to a given ref.
#   scripts/rollback.sh            -> the version before the current one
#   scripts/rollback.sh v0.9.0     -> that release
# Never rewrites git history; it only changes which image is running.
set -euo pipefail
cd "$(dirname "$0")/.."

STATE_DIR="${PLANWERK_STATE:-$HOME/.planwerk}"
if [[ $# -ge 1 ]]; then
  TARGET="$1"
else
  [[ -s "$STATE_DIR/history" ]] || { echo "no previous deployment recorded" >&2; exit 1; }
  TARGET="$(tail -n 1 "$STATE_DIR/history")"
  sed -i.bak '$d' "$STATE_DIR/history" && rm -f "$STATE_DIR/history.bak"
fi
echo "== current: $(cat "$STATE_DIR/current" 2>/dev/null || echo unknown), rolling back to $TARGET"
exec scripts/deploy.sh "$TARGET"
