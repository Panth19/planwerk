#!/usr/bin/env bash
# Deploy a git ref as a container, with health check and automatic rollback.
#   scripts/deploy.sh v1.0.0        scripts/deploy.sh HEAD
# Every deployed version stays as a tagged image, so a rollback starts the old
# image again in seconds instead of rebuilding it.
set -euo pipefail
cd "$(dirname "$0")/.."

REF="${1:-HEAD}"
NAME="${PLANWERK_CONTAINER:-planwerk}"
PORT="${PLANWERK_PORT:-8765}"
SHA="$(git rev-parse --short "$REF^{commit}")"   # ^{commit}: a tag must resolve to its commit, not the tag object
IMAGE="planwerk:$SHA"
STATE_DIR="${PLANWERK_STATE:-$HOME/.planwerk}"
mkdir -p "$STATE_DIR/logs"
ENV_ARGS=()
[[ -n "${PLANWERK_ENV:-}" ]] && ENV_ARGS=(--env-file "$PLANWERK_ENV")   # e.g. ANTHROPIC_API_KEY=...

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "== building $IMAGE from $REF"
  TMP="$(mktemp -d)"
  git archive "$REF" | tar -x -C "$TMP"
  docker build --build-arg "COMMIT=$SHA" -t "$IMAGE" "$TMP"
  rm -rf "$TMP"
fi

PREVIOUS="$(cat "$STATE_DIR/current" 2>/dev/null || true)"
echo "== starting $IMAGE (previous: ${PREVIOUS:-none})"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart unless-stopped -p "127.0.0.1:$PORT:8765" \
  ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} -v "$STATE_DIR/logs:/app/logs" "$IMAGE" >/dev/null

for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" | grep -q "\"commit\":\"$SHA\""; then
    echo "$SHA" > "$STATE_DIR/current"
    [[ -n "$PREVIOUS" && "$PREVIOUS" != "$SHA" ]] && echo "$PREVIOUS" >> "$STATE_DIR/history"
    echo "== live: $SHA"
    exit 0
  fi
  sleep 1
done

echo "!! health check failed for $SHA" >&2
docker logs --tail 40 "$NAME" >&2 || true
if [[ -n "$PREVIOUS" ]]; then
  echo "== rolling back to $PREVIOUS" >&2
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" --restart unless-stopped -p "127.0.0.1:$PORT:8765" \
    ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} -v "$STATE_DIR/logs:/app/logs" "planwerk:$PREVIOUS" >/dev/null
fi
exit 1
