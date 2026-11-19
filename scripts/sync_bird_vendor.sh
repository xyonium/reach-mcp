#!/bin/bash
# Sync the vendored bird-search wrapper from last30days upstream (main).
# Usage: ./scripts/sync_bird_vendor.sh [repo-url]
set -euo pipefail

REPO="${1:-https://github.com/mvanhorn/last30days-skill.git}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/src/reach_mcp/vendor/bird-search"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --depth 1 "$REPO" "$TMP/src"
SRC="$TMP/src/skills/last30days/scripts/lib/vendor/bird-search"
if [ ! -f "$SRC/bird-search.mjs" ]; then
  echo "upstream bird-search not found at $SRC" >&2
  exit 1
fi

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -a "$SRC" "$DEST"
echo "synced $DEST from $REPO"
git -C "$ROOT" status --porcelain -- "$DEST" || true
