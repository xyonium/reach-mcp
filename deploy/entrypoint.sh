#!/bin/bash
set -e

# mcpo container entrypoint - installs/refreshes the dependencies for every
# uvx-launched MCP server (reach-mcp, fetch, futu, yfinance, docling ...), then
# execs `uvx mcpo`.
#
# Mount this at /config/entrypoint.sh and point the mcpo compose service's
# `entrypoint` at it. All install artifacts land under /config so they persist
# across container restarts via the mounted volume.
#
# reach-mcp-specific deps installed here:
#   - yt-dlp        (youtube source transcripts)
#   - gh CLI        (github source auth)
#   - digg/arxiv/techmeme pp-cli  (digg/arxiv/techmeme sources)
#   - bili-cli      (bilibili source - handles wbi signing / 412 anti-scrape)
# Optional desktop-only deps (only if you run OpenCLI locally, not in this
# headless container):
#   - opencli       (tiktok/instagram/pinterest/xueqiu desktop boost)

ARCH=$(uname -m)   # x86_64->amd64, aarch64->arm64
case "$ARCH" in
  x86_64)  GOARCH=amd64; DENOARCH=x86_64 ;;
  aarch64) GOARCH=arm64; DENOARCH=aarch64 ;;
  *) echo "unsupported arch: $ARCH"; exit 1 ;;
esac

export PATH=/config/bin:/config/go/bin:$PATH

# ========== 0. 全局升级开关（touch /config/UPGRADE 后重启触发）==========
if [ -f /config/UPGRADE ]; then
  echo "[mcpo] UPGRADE flag detected! Cleaning binary caches for fresh install..."
  rm -rf /config/bin/* /config/last30days/VERSION /config/go /config/UPGRADE
fi

mkdir -p /config/bin /config/last30days

# ========== 1. last30days MCP server（版本比对，最新则跳过）==========
# NOTE: reach-mcp is a drop-in replacement for last30days. Keep this block only
# if you still run the original last30days server alongside reach-mcp; otherwise
# remove it and just let mcpo `uvx reach-mcp`.
L30D_DIR=/config/last30days
TAG=$(python3 -c "
import json, urllib.request
r = urllib.request.urlopen('https://api.github.com/repos/mvanhorn/last30days-skill/releases/latest', timeout=30)
print(json.load(r)['tag_name'])
" 2>/dev/null || echo "")
CURRENT=$(cat "$L30D_DIR/VERSION" 2>/dev/null || echo none)

if [ -n "$TAG" ] && { [ "$TAG" != "$CURRENT" ] || [ ! -x "$L30D_DIR/last30days-pp-mcp" ]; }; then
  echo "[last30days] downloading $TAG ..."
  python3 - "$TAG" "$L30D_DIR" "$GOARCH" <<'EOF'
import io, os, stat, sys, zipfile, urllib.request
tag, outdir, goarch = sys.argv[1], sys.argv[2], sys.argv[3]
url = f"https://github.com/mvanhorn/last30days-skill/releases/download/{tag}/last30days-pp-mcp-linux-{goarch}.mcpb"
data = urllib.request.urlopen(url, timeout=300).read()
z = zipfile.ZipFile(io.BytesIO(data))
bin_name = next(n for n in z.namelist() if n.endswith("last30days-pp-mcp") and not n.endswith("/"))
out = os.path.join(outdir, "last30days-pp-mcp")
with open(out, "wb") as f:
    f.write(z.read(bin_name))
os.chmod(out, os.stat(out).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
EOF
  echo "$TAG" > "$L30D_DIR/VERSION"
  echo "[last30days] installed $TAG"
else
  echo "[last30days] already at ${CURRENT}, skip download"
fi

# ========== 2. yt-dlp + bili-cli（每次重启自动检查并升级最新版）==========
echo "[mcpo] ensuring yt-dlp ..."
uv tool install --upgrade yt-dlp || echo "[mcpo] yt-dlp install/upgrade failed, using cached version"

# bili-cli: reach-mcp bilibili source prefers it (handles B站 wbi signing + 412
# anti-scrape that the raw public API hits). Falls back to the raw API if absent.
echo "[mcpo] ensuring bili-cli (bilibili source) ..."
uv tool install --upgrade bilibili-cli || echo "[mcpo] bili-cli install/upgrade failed, bilibili will use the raw API fallback"

# ========== 3. deno（给 yt-dlp 解 YouTube JS Challenge）==========
if ! command -v deno >/dev/null 2>&1; then
  echo "[mcpo] installing deno (one-time) ..."
  python3 -c "
import urllib.request, zipfile, io
url = 'https://github.com/denoland/deno/releases/latest/download/deno-${DENOARCH}-unknown-linux-gnu.zip'
data = urllib.request.urlopen(url, timeout=60).read()
z = zipfile.ZipFile(io.BytesIO(data))
z.extract('deno', '/config/bin')
"
  chmod +x /config/bin/deno
  echo "[mcpo] deno installed"
fi

# ========== 4. gh CLI（GitHub 源认证用）==========
if ! command -v gh >/dev/null 2>&1; then
  echo "[mcpo] installing gh CLI (one-time) ..."
  GH_VER=$(python3 -c "
import json, urllib.request
print(json.load(urllib.request.urlopen('https://api.github.com/repos/cli/cli/releases/latest', timeout=30))['tag_name'])
" 2>/dev/null || echo "v2.76.0")
  python3 -c "
import urllib.request
urllib.request.urlretrieve('https://github.com/cli/cli/releases/download/${GH_VER}/gh_${GH_VER#v}_linux_${GOARCH}.tar.gz', '/tmp/gh.tgz')
"
  mkdir -p /tmp/ghx && tar -C /tmp/ghx -xzf /tmp/gh.tgz
  cp /tmp/ghx/gh_*/bin/gh /config/bin/gh && rm -rf /tmp/ghx /tmp/gh.tgz
  echo "[mcpo] gh ${GH_VER} installed"
fi

# ========== 5. Go 工具链（pp-cli 编译依赖）==========
if ! command -v go >/dev/null 2>&1; then
  echo "[mcpo] installing Go toolchain (one-time) ..."
  GO_VER=$(python3 -c "
import json, urllib.request
print(json.load(urllib.request.urlopen('https://go.dev/dl/?mode=json', timeout=30))[0]['version'])
" 2>/dev/null || echo "go1.26.5")
  python3 -c "
import urllib.request
urllib.request.urlretrieve('https://go.dev/dl/${GO_VER}.linux-${GOARCH}.tar.gz', '/tmp/go.tgz')
"
  tar -C /config -xzf /tmp/go.tgz && rm -f /tmp/go.tgz
  echo "[mcpo] Go ${GO_VER} installed"
fi

# ========== 6. pp-cli（digg/arxiv/techmeme 编译）==========
for tool in digg arxiv techmeme; do
  bin="/config/bin/${tool}-pp-cli"
  if [ ! -x "$bin" ]; then
    echo "[mcpo] building ${tool}-pp-cli (one-time) ..."
    npx -y @mvanhorn/printing-press-library@0.1.19 install "$tool" --cli-only --bin-dir /config/bin \
      && echo "[mcpo] ${tool}-pp-cli ready" \
      || echo "[mcpo] ${tool}-pp-cli build failed, source will be unavailable"
  fi
done

# ========== 7. (optional) opencli - desktop boost for tiktok/ig/pinterest/xueqiu ==========
# OpenCLI needs a desktop Chrome + browser-bridge extension, so it is NOT installed
# in this headless container by default. If you run mcpo on a desktop machine and
# want the OpenCLI boost, uncomment:
#   npm install -g @jackwener/opencli
# and install the Chrome extension separately. Without it, those sources use their
# server-side backends (Apify / public APIs / Searxng) which is the intended default.

exec uvx mcpo "$@"
