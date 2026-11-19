#!/bin/bash
# Keep a stable /config/reach-venv symlink pointing at the latest reach-mcp
# release installed from PyPI. Runs at container start:
#   - --bootstrap: install synchronously if no working venv exists
#   - otherwise: called in the background; current venv keeps serving while a
#     new one is built, then the symlink is swapped for the next spawn.
set -euo pipefail

BASE=/config
CURRENT="$BASE/reach-venv"
LOCK="$BASE/reach-update.lock"
BOOTSTRAP=0
[ "${1:-}" = "--bootstrap" ] && BOOTSTRAP=1
NEXT=""
SUCCESS=0
cleanup() {
  if [ "$SUCCESS" != "1" ] && [ -n "$NEXT" ] && [ -d "$NEXT" ]; then
    rm -rf "$NEXT"
  fi
}
trap cleanup EXIT

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[reach-update] another update is already running; skip"
  exit 0
fi

LATEST=$(python3 - <<'PY'
import json
import time
import urllib.request

# Cache-bust the PyPI JSON endpoint; CDN edges can lag a fresh release.
url = f"https://pypi.org/pypi/reach-mcp/json?ts={int(time.time())}"
req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
with urllib.request.urlopen(req, timeout=30) as r:
    print(json.load(r)["info"]["version"])
PY
) || {
  echo "[reach-update] PyPI lookup failed; keeping current venv"
  exit 1
}

CUR=""
if [ -x "$CURRENT/bin/python" ]; then
  CUR=$("$CURRENT/bin/python" -c "import reach_mcp; print(reach_mcp.__version__)" 2>/dev/null || true)
fi

if [ -n "$CUR" ] && [ "$CUR" = "$LATEST" ]; then
  echo "[reach-update] reach-mcp $CUR is current"
  exit 0
fi

# Never downgrade: a stale CDN edge or a yanked release must not replace a
# working newer venv.
if [ -n "$CUR" ]; then
  NEWEST=$(printf '%s\n%s\n' "$CUR" "$LATEST" | sort -V | tail -1)
  if [ "$NEWEST" = "$CUR" ]; then
    echo "[reach-update] current $CUR is newer than PyPI $LATEST; skip"
    exit 0
  fi
fi

if [ -z "$CUR" ] && [ "$BOOTSTRAP" -eq 0 ]; then
  echo "[reach-update] no working venv; run with --bootstrap"
  exit 1
fi

SAFE=$(printf '%s' "$LATEST" | tr -c 'A-Za-z0-9._-' '_')
NEXT="$BASE/reach-venv-${SAFE}-$(date -u +%Y%m%d%H%M%S)"
echo "[reach-update] installing reach-mcp[tiktok]==$LATEST -> $NEXT"

uv venv "$NEXT"
ARGS=(pip install --refresh --python "$NEXT/bin/python")
if [ -f "$BASE/uv-constraints.txt" ]; then
  ARGS+=(-c "$BASE/uv-constraints.txt")
fi
uv "${ARGS[@]}" "reach-mcp[tiktok]==$LATEST"

"$NEXT/bin/python" -c "import reach_mcp; assert reach_mcp.__version__ == '$LATEST'; print('reach', reach_mcp.__version__)"
"$NEXT/bin/reach-mcp" --help >/dev/null
"$NEXT/bin/python" -c "from reach_mcp.pipeline import import_all_sources; import_all_sources(); from reach_mcp.sources import SOURCES; assert len(SOURCES) >= 30"

echo "[reach-update] ensuring matching chromium ..."
if ! PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/config/ms-playwright}" \
     PLAYWRIGHT_NODEJS_PATH="${PLAYWRIGHT_NODEJS_PATH:-/usr/bin/node}" \
     "$NEXT/bin/python" -m playwright install chromium; then
  echo "[reach-update] chromium install failed; keeping current venv"
  exit 1
fi

if [ -L "$CURRENT" ]; then
  readlink "$CURRENT" > "$BASE/reach-venv.prev"
fi

if [ -e "$CURRENT" ] && [ ! -L "$CURRENT" ]; then
  mv "$CURRENT" "$CURRENT.bak.$(date -u +%Y%m%d%H%M%S)"
fi

TMP_LINK="$BASE/.reach-venv.tmp.$$"
ln -s "$(basename "$NEXT")" "$TMP_LINK"
mv -T "$TMP_LINK" "$CURRENT"
SUCCESS=1
echo "[reach-update] activated reach-mcp $LATEST at $CURRENT"
