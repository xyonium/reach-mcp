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

# ========== 1. last30days（已从 config.json 移除，2026-11-19）==========
# No download at startup. The existing binary/data under /config/last30days are
# kept for rollback; restore the last30days block from
# /mnt/docker/mcpserver/last30days.server.json to re-enable it manually.

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

# ========== 7b. TikTok free backend (playwright + chromium, persisted) ==========
# reach-mcp's tiktok source prefers a free headless-chromium in-page fetch over
# the paid Apify actors. Two persisted pieces under /config (the mounted volume):
#   - the playwright PYTHON package: NOT installed here — it rides in via
#     mcpo config.json launching reach with
#       "args": ["uvx", "--refresh", "--from", "reach-mcp[tiktok]", "reach-mcp", ...]
#     so uv resolves it into reach-mcp's own environment (a bare `uv tool
#     install playwright` would land in an isolated env the server can't import).
#   - the chromium BINARY (~400MB): installed below into
#     PLAYWRIGHT_BROWSERS_PATH=/config/ms-playwright so it survives container
#     recreation. Skipped when the marker version file matches (upgrades flow
#     through the /config/UPGRADE flag like everything else).
export PLAYWRIGHT_BROWSERS_PATH=/config/ms-playwright
# Playwright's bundled node needs libatomic.so.1, which this slim image lacks;
# the container's system node is used instead.
export PLAYWRIGHT_NODEJS_PATH="${PLAYWRIGHT_NODEJS_PATH:-$(command -v node || echo /usr/bin/node)}"
PW_MARKER="/config/ms-playwright/.chromium-ok"
if [ ! -f "$PW_MARKER" ]; then
  echo "[mcpo] installing chromium for the tiktok free backend (one-time, ~400MB) ..."
  # uvx runs reach-mcp[tiktok] in an ephemeral env; use an isolated venv on the
  # volume purely as the installer/driver host. Its driver binary is what
  # reach-mcp's playwright import talks to at runtime.
  if [ ! -x /config/pwenv/bin/python ]; then
    uv venv /config/pwenv >/dev/null 2>&1 || python3 -m venv /config/pwenv
    uv pip install --python /config/pwenv/bin/python playwright >/dev/null 2>&1 \
      || /config/pwenv/bin/pip install -q playwright
  fi
  /config/pwenv/bin/python -m playwright install --with-deps chromium \
    && touch "$PW_MARKER" \
    && echo "[mcpo] chromium installed -> $PLAYWRIGHT_BROWSERS_PATH" \
    || echo "[mcpo] chromium install FAILED — tiktok falls back to Apify (non-fatal)"
else
  echo "[mcpo] chromium already present ($PLAYWRIGHT_BROWSERS_PATH), skip"
fi

# ========== 8. uv constraints (pin mcp SDK <2 for mcpo + its child servers) ==========
# mcpo 0.0.20 (and many uvx-launched MCP servers like mcp-server-fetch) import
# 1.x mcp SDK symbols that mcp 2.0 renamed, so uv resolving mcp 2.x crashes them
# at startup. Pin mcp<2 via a constraints file. Setting UV_CONSTRAINT (not just
# --constraints) matters: mcpo spawns each config.json server with
# env={**os.environ,...}, so a UV_CONSTRAINT env var is inherited by every child
# uvx process too — --constraints alone only fixes mcpo itself. Copy
# deploy/uv-constraints.txt to your mcpo config dir to customize; otherwise the
# default below is written to /config/uv-constraints.txt.
if [ ! -f /config/uv-constraints.txt ]; then
  cat > /config/uv-constraints.txt <<'UVEOF'
mcp<2
UVEOF
  echo "[mcpo] wrote default uv-constraints.txt (mcp<2)"
fi
export UV_CONSTRAINT=/config/uv-constraints.txt

# ========== 9. reach-mcp venv（跟随 PyPI 最新版，更新不阻塞启动）==========
REACH_UPDATER=/config/update-reach-venv.sh
if [ -x "$REACH_UPDATER" ]; then
  if [ -x /config/reach-venv/bin/reach-mcp ]; then
    echo "[mcpo] starting background reach update check..."
    "$REACH_UPDATER" >>/config/reach-update.log 2>&1 &
  else
    echo "[mcpo] bootstrapping reach venv from PyPI..."
    "$REACH_UPDATER" --bootstrap || echo "[mcpo] reach bootstrap failed; reach will be unavailable"
  fi
else
  echo "[mcpo] WARN: $REACH_UPDATER missing; reach venv will not be updated"
fi

# ========== 10. Playwright system deps（容器重建后 apt 层会丢，按需补）==========
if [ -x /config/reach-venv/bin/python ]; then
  if ! (ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null) | grep -q 'libglib-2.0.so.0'; then
    echo "[mcpo] installing playwright system deps ..."
    PLAYWRIGHT_NODEJS_PATH="$PLAYWRIGHT_NODEJS_PATH" \
      /config/reach-venv/bin/python -m playwright install-deps chromium \
      || echo "[mcpo] playwright deps install failed; tiktok may fall back"
  fi
fi

exec uvx mcpo "$@"
