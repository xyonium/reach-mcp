#!/bin/bash
# Runtime cache for the bird-search JS wrapper.
#
# - First run (or --bootstrap): copy the copy bundled in the reach venv.
# - Normal run: hash the upstream bird-search directory (GitHub tree API);
#   if unchanged, exit and reuse /config/reach-bird/current.
#   If changed, download that commit's tarball, verify, and atomically swap
#   the "current" symlink. The running reach process uses the stable path
#   /config/reach-bird/current/bird-search.mjs, so the next X search picks up
#   the new files without a restart.
#
# No GitHub PR / reach release is needed for production updates. The copy in
# src/reach_mcp/vendor/bird-search is only the offline/first-boot fallback.
set -euo pipefail

BASE=/config/reach-bird
CURRENT="$BASE/current"
LOCK="$BASE/update.lock"
REPO="mvanhorn/last30days-skill"
BIRD_PATH="skills/last30days/scripts/lib/vendor/bird-search"
BOOTSTRAP_ONLY=0
[ "${1:-}" = "--bootstrap" ] && BOOTSTRAP_ONLY=1

mkdir -p "$BASE/versions"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[bird-update] another update is already running; skip"
  exit 0
fi

# Bootstrap from the installed reach package when there is no current copy.
if [ ! -f "$CURRENT/bird-search.mjs" ] && [ -x /config/reach-venv/bin/python ]; then
  BUNDLED=$(/config/reach-venv/bin/python - <<'PY'
import pathlib
import reach_mcp
print(pathlib.Path(reach_mcp.__file__).resolve().parent / "vendor" / "bird-search")
PY
  )
  if [ -f "$BUNDLED/bird-search.mjs" ]; then
    DEST="$BASE/versions/bundled-$(date -u +%Y%m%d%H%M%S)"
    cp -a "$BUNDLED" "$DEST"
    TMP_LINK="$BASE/.current.tmp.$$"
    ln -s "versions/$(basename "$DEST")" "$TMP_LINK"
    mv -T "$TMP_LINK" "$CURRENT"
    echo "[bird-update] bootstrapped from bundled $DEST"
  fi
fi

if [ "$BOOTSTRAP_ONLY" -eq 1 ]; then
  exit 0
fi

# Resolve upstream commit + a content hash of the whole bird-search directory.
INFO=$(python3 - "$REPO" "$BIRD_PATH" <<'PY'
import hashlib
import json
import sys
import urllib.request

repo, path = sys.argv[1], sys.argv[2]
headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "reach-mcp-bird-updater",
}


def get(url):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


commit = get(f"https://api.github.com/repos/{repo}/commits/main")["sha"]
tree = get(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1")["tree"]
items = [
    (x["path"], x["sha"])
    for x in tree
    if x.get("type") == "blob" and (x["path"] == path or x["path"].startswith(path + "/"))
]
if not items:
    raise SystemExit(f"no files under {path} in {commit}")

h = hashlib.sha256()
for p, s in sorted(items):
    h.update(f"{p}\0{s}\n".encode())
print(commit)
print(h.hexdigest())
print(len(items))
PY
) || {
  echo "[bird-update] GitHub lookup failed; keeping current"
  exit 1
}

COMMIT=$(printf '%s\n' "$INFO" | sed -n '1p')
HASH=$(printf '%s\n' "$INFO" | sed -n '2p')
COUNT=$(printf '%s\n' "$INFO" | sed -n '3p')
echo "[bird-update] upstream $COMMIT hash $HASH files $COUNT"

if [ -f "$BASE/.bird_hash" ] && [ "$(cat "$BASE/.bird_hash")" = "$HASH" ] && [ -f "$CURRENT/bird-search.mjs" ]; then
  echo "[bird-update] unchanged; reuse cache"
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 - "$COMMIT" "$TMP" "$BIRD_PATH" <<'PY'
import io
import os
import sys
import tarfile
import urllib.request

commit, out, path = sys.argv[1], sys.argv[2], sys.argv[3]
url = f"https://codeload.github.com/mvanhorn/last30days-skill/tar.gz/{commit}"
with urllib.request.urlopen(url, timeout=180) as r:
    data = r.read()
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
    members = [
        m
        for m in tf.getmembers()
        if f"/{path}/" in m.name or m.name.endswith(f"/{path}")
    ]
    if not members:
        raise SystemExit("bird-search not found in upstream tarball")
    tf.extractall(out, members=members, filter="data")

for root, _dirs, files in os.walk(out):
    if os.path.basename(root) == "bird-search" and "bird-search.mjs" in files:
        print(root)
        break
else:
    raise SystemExit("extracted bird-search not found")
PY
SRC=$(find "$TMP" -type d -name bird-search -path '*/vendor/*' | head -1)
if [ -z "$SRC" ] || [ ! -f "$SRC/bird-search.mjs" ] || [ ! -d "$SRC/lib" ]; then
  echo "[bird-update] invalid upstream payload; keeping current"
  exit 1
fi

DEST="$BASE/versions/upstream-$COMMIT"
rm -rf "$DEST"
cp -a "$SRC" "$DEST"

if [ -L "$CURRENT" ]; then
  readlink "$CURRENT" > "$BASE/.previous"
fi
TMP_LINK="$BASE/.current.tmp.$$"
ln -s "versions/upstream-$COMMIT" "$TMP_LINK"
mv -T "$TMP_LINK" "$CURRENT"
echo "$HASH" > "$BASE/.bird_hash"
echo "$COMMIT" > "$BASE/.bird_commit"
echo "[bird-update] activated $COMMIT ($COUNT files) at $CURRENT"
