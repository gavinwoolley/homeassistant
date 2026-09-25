#!/usr/bin/env bash
# Builds a fully self-contained demo image: onboarding done, all 18 cameras
# set up, http config settled - `docker run -p 8123:8123 <tag>` on a
# completely clean machine just shows the dashboard, no setup steps at all.
#
# Reproducible from a clean checkout - unlike just `docker build .`, which
# only bakes the static YAML/www files and would still need onboarding on
# first run. This script actually goes through onboarding and the camera
# setup live (against a throwaway temporary container, no volumes - so
# `docker commit` at the end captures the result as real image layers) and
# commits the result as a new image, deleting the temporary container after.
#
# Usage: ./demo/tools/bake_demo_image.sh [image:tag]
# Needs: docker, python3 with aiohttp + pyyaml (pip install aiohttp pyyaml), run from the repo root.
set -euo pipefail

TAG="${1:-homeassistant-demo-baked:latest}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DIR="$REPO_ROOT/demo"
BUILD_TAG="homeassistant-demo-baked-build:tmp"
CONTAINER="demo-bake-tmp"
PORT=18890

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Building base image (static config only, no onboarding yet)"
docker build -f "$DEMO_DIR/Dockerfile" -t "$BUILD_TAG" "$DEMO_DIR"

echo "==> Starting a throwaway container (no volumes - /config lives in this container's own layer, so 'docker commit' captures it)"
cleanup
docker run -d --name "$CONTAINER" -p "$PORT:8123" "$BUILD_TAG"

echo "==> Waiting for it to come up..."
# Any real HTTP response is proof of life here, not specifically 200 - HA's
# "/" redirects (302) to onboarding or the dashboard depending on state, it
# doesn't render there directly either before or after onboarding. Confirmed
# live (2026-09-16): a cleanly-booted, no-errors HA instance sat at
# "http=302" for the full 5-minute wait, so requiring a literal 200 here
# meant this check could never actually pass - "000" (curl's own code for
# connection-refused/no response) is the only real "not up yet" signal.
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)
  [ -n "$code" ] && [ "$code" != "000" ] && break
  sleep 5
done
[ -n "$code" ] && [ "$code" != "000" ] || { echo "never came up (http=$code)"; docker logs --tail 100 "$CONTAINER"; exit 1; }

echo "==> Onboarding (demo/demo) and setting up cameras"
python3 "$REPO_ROOT/demo/tools/setup_demo_cameras.py" \
  --base-url "http://127.0.0.1:$PORT" --username demo --password demo --onboard-name Demo

echo "==> Letting it settle for 30s before freezing state"
sleep 30

echo "==> Committing $CONTAINER -> $TAG"
# DEMO_CONTENT_HASH, when set (the GitHub Actions publish workflow sets
# it), gets baked in as a label so a future run can compare against it and
# skip rebaking when demo/ hasn't actually changed - see that workflow's
# own "Check whether the published image already matches this content"
# step. Optional and harmless for local/manual runs that don't set it.
if [ -n "${DEMO_CONTENT_HASH:-}" ]; then
  docker commit --change "LABEL demo.content_hash=$DEMO_CONTENT_HASH" "$CONTAINER" "$TAG"
else
  docker commit "$CONTAINER" "$TAG"
fi

echo "==> Verifying: fresh container, no volumes, should need zero setup"
docker rm -f demo-bake-verify >/dev/null 2>&1 || true
docker run -d --name demo-bake-verify -p "$((PORT + 1)):8123" "$TAG"
sleep 15
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$((PORT + 1))/" || true)
docker rm -f demo-bake-verify >/dev/null 2>&1 || true
if [ -n "$code" ] && [ "$code" != "000" ]; then
  echo "==> Done. $TAG is ready: docker run -p 8123:8123 $TAG"
else
  echo "==> Verification failed (http=$code) - $TAG was still created, but check it manually"
  exit 1
fi
