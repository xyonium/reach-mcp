# mcpo 重启慢：last30days、Playwright 与 DSH 迁移

- 日期：2026-11-19
- 状态：**已实施（2026-11-19）；不 pin 版本；实际结果见 §0**
- 对象：`eli@dockerno1` 的 `mcpo` 容器、`reach-mcp` 的 X source、本仓库的 Claude Code → DSH 迁移
- 结论先行：
  - 这次 9 分钟里 **4m39s** 是 entrypoint 在下载 last30days 整包；但历史日志显示 **不是每次重启都 9 分钟**，同版本重启通常 1–4 分钟。
  - 另一个更大的慢点是 `reach-mcp[tiktok]` 的 **Playwright 51MB wheel**：11-16 那次下载花了 **32m10s**，总启动 36 分钟。
  - reach-mcp 只借了 last30days 缓存里 **116KB** 的 `bird-search`；可以单独 vendor。`digg/arxiv/techmeme` 的 pp-cli 是另一套，不依赖 13MB 整包。
  - 实际采用：**不 pin 版本**；last30days 从 config 移除，reach 改持久 venv + 后台跟随 PyPI 最新，bird vendor 进包。详见 §0。

---

## 0. 实际实施（2026-11-19，不 pin）

用户明确要求**不固定版本、跟随上游升级**，因此没有采用下面的 B/C pin 方案，实际落地为：

- **last30days**：从 `config.json` 移除；块保存在 `/mnt/docker/mcpserver/last30days.server.json`，二进制/数据保留在 `/config/last30days`；entrypoint 不再下载/启动。`/last30days` 返回 404；reach 的 5 个工具不受影响。
- **reach**：持久 venv `/config/reach-venv`，由 `/config/update-reach-venv.sh` 从 PyPI 安装**最新版**（不 pin）。启动先用现有 venv；后台检查新版，安装验证后原子切换 symlink，不阻塞重启。首次 bootstrap 可能慢一次。更新检查在**容器启动 + 每天 04:20 host cron**；只更新 venv，运行中的进程仍旧，**下次 restart 生效**；立刻生效用 `docker exec mcpo /config/update-reach-venv.sh && docker restart mcpo`。坏 venv 会被入口的 `import` + `reach-mcp --help` 健康检查捕获并走 `--bootstrap`；updater 切换前写 `/config/reach-venv.prev`。
- **X bird**：`reach-mcp 0.7.7` 已 vendor `bird-search`（`src/reach_mcp/vendor/bird-search`，116KB、16 个文件、MIT）；`x.py` 从包内解析；`scripts/sync_bird_vendor.sh` + `.github/workflows/sync-bird.yml` 每周从 last30days upstream 同步并开 PR。
- **免费 TikTok**：保留 `[tiktok]` extra；venv 里 Playwright 1.65.2，需匹配 chromium-1255（已补装）。Playwright 自带 node 缺 `libatomic.so.1`，entrypoint 用 `PLAYWRIGHT_NODEJS_PATH=/usr/bin/node`，并在容器重建后按需 `playwright install-deps chromium`。实测 TikTok 搜索 3 条，无 fallback warning。
- **实测**：`docker restart mcpo` 到 ready **84–149s**（第一次 149s，第二次 84s；原 8m39s / 36m10s）；11 个 server 全连上；X 搜索 3–5 条、TikTok 3 条，`/reach/list_sources` 33 个源。
- **安全**：`config.json`、`config.json.bak-*`、`last30days.server.json` 含明文密钥，已统一 `chmod 600`。
- **回滚**：当前好状态 `config.json.good-20261119-231023` + `entrypoint.sh.good-20261119-231023`；坏 venv 用 `/config/reach-venv.prev`；只恢复 last30days 把 `last30days.server.json` 合并进当前 config；完整退回旧 uvx/12-server 才用 `config.json.bak-no-last30days-*` + `entrypoint.sh.bak-*`（会重走慢路径）。

> 下面的 B/C 固定版本方案保留为历史备选；实际执行以本节为准。

---

## 1. 证据

### 1.1 这次 9 分钟的时间线（`docker logs -t mcpo`）

容器 `StartedAt` 是 `2026-11-19T04:54:04Z`（本地 12:54:04）。之后：

| UTC | 本地 (CST) | 阶段 | 耗时 |
|---|---|---|---|
| 04:54:04 | 12:54:04 | 容器启动，旧进程 SIGTERM | — |
| 04:54:07 | 12:54:07 | `[last30days] downloading v4.3.2 ...` | — |
| 04:58:46 | 12:58:46 | `[last30days] installed v4.3.2` | **279s（4m39s）** |
| 04:58:46 | 12:58:46 | `uv tool install --upgrade yt-dlp` | 4s |
| 04:58:48 | 12:58:48 | `uv tool install --upgrade bilibili-cli` | 8s |
| 04:58:52 | 12:58:52 | chromium 已存在，跳过 | 0s |
| 04:58:59 | 12:58:59 | `uvx mcpo` 装好 42 个包 | 13s |
| 04:59:12 | 12:59:12 | mcpo 开始逐个拉起 12 个 MCP server | — |
| 05:02:43 | 13:02:43 | `Application startup complete` | 211s（3m31s） |
| — | — | **从容器启动到就绪** | **约 8m39s** |

也就是说：**last30days 下载占 54%**；剩下 3m57s 是 mcpo 顺序拉起所有 server 的成本。

### 1.2 历史样本：不是每次 9 分钟，有两条慢路径

同一容器（11-10 起）的完整日志里，last30days 相关启动共 5 次下载、多次同版本跳过：

| 日期 (UTC) | last30days | 下载耗时 | `reach` 连接耗时 | 到就绪总耗时 |
|---|---|---|---|---|
| 11-10 14:40 | v3.33.2 | **364s** | 3m15s | **12m37s** |
| 11-12 21:39 | v3.38.1 | 5s | 快 | **1m29s** |
| 11-16 07:34 | v4.1.0 | 49s | **32m22s（Playwright 51MB）** | **36m10s** |
| 11-16 11:16 | v4.2.0 | 6s | 快 | **2m41s** |
| 11-19 04:54 | v4.3.2 | **279s** | 12s | **8m36s**（容器启动算 8m39s） |

结论：

- **同版本重启不会重复下载**：11-12 有一串 `already at v3.33.2, skip download`，启动都很快。
- **发新版后的第一次重启会下载**；下载速度从 5s 到 364s 不等，取决于当时 GitHub 出口。
- **还有一条与 last30days 无关的慢路径**：`reach` 的 `[tiktok]` extra 在缓存 miss 时要下载 51MB 的 Playwright wheel；11-16 那次花了 32m10s。
- 所以“最近经常很久”不是单一原因；只修 last30days，仍可能在 reach/Playwright 上撞到半小时。

### 1.3 last30days 为什么会被反复下载

`deploy/entrypoint.sh` 第 1 段每次启动都做：

1. 请求 `https://api.github.com/repos/mvanhorn/last30days-skill/releases/latest`（30s 超时）；
2. 拿 `tag_name` 和 `/config/last30days/VERSION` 比；
3. 不一致就下载 `last30days-pp-mcp-linux-amd64.mcpb`（**5.8MB / 5.80MiB**），解压出 **13,019,258B** 的二进制。

GitHub API 查到的发布节奏：

```
v4.3.2  2026-11-17T15:56:44Z
v4.3.1  2026-11-17T15:28:40Z   （同日，间隔 28 分钟）
v4.3.0  2026-11-16T23:57:17Z
v4.2.1  2026-11-16T16:42:38Z
v4.2.0  2026-11-16T07:55:27Z
v4.1.0  2026-11-16T05:52:45Z
v4.0.6  2026-11-16T04:08:40Z
...
```

**11-16～11-17 两天连发 7 个版本（v4.0.6～v4.3.2）**。所以“撞上新版本”的概率很高：

- 同版本重启会跳过；
- 但每次发新版后的第一次重启都会重下；
- `touch /config/UPGRADE` 会删掉 `VERSION`，也会触发重下；
- 下载失败时 `set -e` 会直接中断 entrypoint，容器起不来（这次只是慢，没失败）。

### 1.4 为什么下载慢

- `docker inspect mcpo` 和 `docker exec mcpo env` 里**没有顶层的 `HTTP(S)_PROXY`**；代理只写在 `config.json` 的子进程 env 里——`reach` 是显式 env，`last30days` 是在 `sh -c` 里 `export`。entrypoint 本身不继承这些。
- entrypoint 用 Python `urllib` 直连 GitHub，没有走 `192.168.254.253:1090`。
- 多次 1MB Range 抽样（不是固定值，随网络波动）：

| 路径 | 抽样速度 | 5.8MB 理论耗时 |
|---|---|---|
| 直连 GitHub | 67–87 KB/s | ~70–90s |
| 走 `192.168.254.253:1090` | 112–193 KB/s | ~30–50s |
| 本次实际下载 | ~21 KB/s | **279s** |

实际比抽样还慢，说明当时 GitHub 出口在抖动/限速；但无论哪种，**把 5.8MB 下载放在启动关键路径上**都会把一次重启放大到分钟级。

### 1.5 更大的慢点：Playwright 51MB

11-16 07:34 那次：

```
07:34:59 [last30days] downloading v4.1.0 ...
07:35:48 [last30days] installed v4.1.0        # 49s
07:36:18 Starting MCPO Server...
07:37:26 Initiating connection for server: 'reach'...
07:37:29 Downloading playwright (51.0MiB)
08:09:39 Installed 47 packages in 988ms       # 32m10s 后
08:09:48 Successfully connected to 'reach'
08:11:09 Application startup complete         # 总 36m10s
```

原因：线上 reach 的启动参数是 `uvx --from "reach-mcp[tiktok]"`，`[tiktok]` 带 `playwright>=1.40`，但没有 pin。uvx 的环境缓存是按“解析后的依赖集合”做 key 的；reach 或 playwright 任意一个新版本都会生成新环境，重新下载 **51MB** wheel。11-19 这次因为缓存命中，reach 只用了 12s（日志里 `Installed 47 packages in 1.10s`）。

### 1.6 所以“缓冲”到底是什么状态

- 同版本、依赖没变：**缓存有效**，重启 1–4 分钟。
- last30days 发新版：版本缓存 miss，重下 5.8MB；快 5s，慢 6m。
- reach/playwright 发新版或 `UPGRADE`：uvx 环境缓存 miss，重下 51MB；这次样本 32m。
- 不是“缓冲没生效”，而是 **缓存 key 跟着 unpinned 的 latest 走**；每次依赖 bump 都相当于冷启动。

---

## 2. reach-mcp 到底还依赖 last30days 什么

### 2.1 依赖面

| 项目 | 是否依赖 last30days | 说明 |
|---|---|---|
| Python 包依赖 | **否** | `pyproject.toml` 没有 last30days；`src/` 没有 import |
| last30days 的 13MB 二进制 | **否** | reach 从不执行它 |
| X / Twitter 的 `bird-search.mjs` | **是（硬编码路径）** | 见 2.2；唯一真正的运行时代码耦合 |
| digg / arxiv / techmeme 的 pp-cli | **否（但同作者）** | 由 `@mvanhorn/printing-press-library@0.1.19` 单独编译，缓存在 `/config/bin` |
| 查询改写/打分逻辑 | **否** | 是移植的代码，不是运行时依赖 |
| last30days MCP server | **独立进程** | config.json 里和 reach 并列，提供 `/preflight`、`/research`；reach 提供 `/search`、`/synthesize`、`/fetch_content`、`/read_url`、`/list_sources` |

### 2.2 X source 的硬编码借用

`src/reach_mcp/sources/x.py:32`：

```python
# Path to last30days' vendored bird-search.mjs (shared with the last30days
# deployment). reach-mcp does NOT vendor it; it reuses the one last30days ships.
_BIRD_SEARCH_MJS = (
    Path("/config/last30days/cache/last30days-pp-mcp/v3.18.0/lib/vendor")
    / "bird-search"
    / "bird-search.mjs"
)
```

现场核对：

- 路径**存在**：`/config/last30days/cache/last30days-pp-mcp/v3.18.0/lib/vendor/bird-search/bird-search.mjs`；
- 整个 `bird-search/` 目录 **116KB、15 个文件**；
- 依赖只有 Node 内置模块（`node:fs` / `node:crypto` 等）和目录内相对文件，**没有 npm 依赖**，可以直接复制；
- MIT License，基于 `@steipete/bird v0.8.0`，`package.json` 要求 Node >= 22；容器里 Node 是 **v22.22.0**；
- query IDs 是运行时从 x.com 发现并缓存 24h（`DEFAULT_TTL_MS = 24h`），所以“冻结 JSON 会过期”的风险比想象低；容器 `HOME=/root` 已核对可写，能写 `query-ids-cache.json`。

X source 的后端顺序是：

```
bird-search.mjs（若存在） → api.x.com cookie fallback → Xquik（XQUIK_API_KEY）
```

所以：

- **不移除 last30days 也可以**先不动 X；
- **要移除 last30days**，必须先把 `bird-search` vendor 进 reach-mcp，否则 X 会降级到 cookie fallback（`AUTH_TOKEN`/`CT0` 还在，未必不可用，但不再是首选路径）。

### 2.3 那个“借用的库”不是整包

用户记忆里的“借了什么库”就是 **`bird-search`**，不是 last30days 的 13MB 二进制，也不是 pp-cli。它只有 116KB，完全可以单独放进 reach-mcp 仓库并随 wheel/sdist 发布。

### 2.4 谁在真正调用 last30days

- Open WebUI 的 `tool_server.connections` 共 12 条：`http://mcpo:8000/reach` 是 **enable=true**；**没有 last30days 条目**。
- `~/.dsh` 的配置里也没有 last30days。
- 当前容器 3 小时日志里 `/last30days/` 只有 2 次 `openapi.json` 探测（本次复核产生的），没有 `/research`；`/reach/` 24 次。样本短，只作旁证。
- 也就是说，目前能确认的调用方只有 mcpo 自己把它拉起来。如果 Claude Code / 脚本 / 其他客户端也不调 `/last30days/research`，方案 A 的前提成立。

---

## 3. 方案

> 以下是固定版本（pin）版的历史备选；用户 2026-11-19 明确要求不 pin，实际执行见 §0（venv + 后台跟随 PyPI 最新）。

### 方案 B（先做，只改 entrypoint）：固定 last30days 版本 + 预置二进制

**目标**：把 last30days 从启动关键路径上拿掉；保留 `/research`、`/preflight`、YouTube comments。

改动只动 `deploy/entrypoint.sh`（以及宿主机上的 `/mnt/docker/mcpserver/entrypoint.sh`）：

1. 不再请求 GitHub latest；固定 `L30D_VERSION`（先 `v4.3.2`）。
2. 启动时只判断“二进制是否存在”：
   - 存在 → 直接跳过，**零网络**；
   - 不存在 → 用固定 URL 下载，并显式走代理；下载后写 `VERSION`。
3. 版本不一致时**不自动覆盖**，只打印提示；升级走单独的 `deploy/update-last30days.sh`（人工确认后执行）。
4. 下载失败 **fail-open**：不要让 `set -e` 把整个 entrypoint 带走，让 mcpo 继续起其他 server。
5. 预置：在宿主机上提前把 `v4.3.2` 的二进制放进 `/mnt/docker/mcpserver/last30days/`，entrypoint 永远走“存在”分支。

示意补丁（重点是 fail-open）：

```bash
# ========== 1. last30days MCP server（固定版本，不再每次查 GitHub）==========
L30D_DIR=/config/last30days
L30D_VERSION="${L30D_VERSION:-v4.3.2}"
CURRENT=$(cat "$L30D_DIR/VERSION" 2>/dev/null || echo none)

if [ ! -x "$L30D_DIR/last30days-pp-mcp" ]; then
  echo "[last30days] binary missing; downloading pinned $L30D_VERSION ..."
  if HTTPS_PROXY="${L30D_DOWNLOAD_PROXY:-http://192.168.254.253:1090}" \
     HTTP_PROXY="${L30D_DOWNLOAD_PROXY:-http://192.168.254.253:1090}" \
     python3 - "$L30D_VERSION" "$L30D_DIR" "$GOARCH" <<'EOF'
# ... 原来的 zip 下载/解压逻辑，URL 改用固定 tag ...
EOF
  then
    echo "$L30D_VERSION" > "$L30D_DIR/VERSION"
    echo "[last30days] installed $L30D_VERSION"
  else
    echo "[last30days] download FAILED; continuing without it"
  fi
elif [ "$CURRENT" != "$L30D_VERSION" ]; then
  echo "[last30days] pinned $L30D_VERSION but cache is $CURRENT; using cache (manual update required)"
else
  echo "[last30days] $CURRENT present, skip"
fi
```

预置（在 `dockerno1` 上执行一次，之后启动零下载）：

```bash
VER=v4.3.2
DEST=/mnt/docker/mcpserver/last30days
curl -fL --proxy http://192.168.254.253:1090 --retry 3 \
  -o /tmp/l30d.mcpb \
  "https://github.com/mvanhorn/last30days-skill/releases/download/$VER/last30days-pp-mcp-linux-amd64.mcpb"
unzip -l /tmp/l30d.mcpb | grep last30days-pp-mcp   # 确认只有一个匹配
unzip -p /tmp/l30d.mcpb '*last30days-pp-mcp' > "$DEST/last30days-pp-mcp"
chmod +x "$DEST/last30days-pp-mcp"
echo "$VER" > "$DEST/VERSION"                      # 这一步不能省，否则日志会误导
rm -f /tmp/l30d.mcpb
```

**预期**：11-19 这种“发新版 + GitHub 慢”的重启，8m39s → 约 4m；同版本重启不变（本来就快）。**它不解决 Playwright 32 分钟**。

### 方案 C（同样先做）：固定 reach/Playwright，预热 uvx 缓存

**目标**：把 `reach` 子 server 的“偶发 32 分钟”变成“最多一次、之后稳定”。

#### C1（推荐，改动较小）

1. 固定 reach 版本：config 的 args 改成
   `["--from", "reach-mcp[tiktok]==0.7.6", "reach-mcp", "--transport", "stdio"]`。
2. 固定 playwright（当前缓存里的版本是 **1.65.2**）。给 reach 单独一份 constraints，避免影响其他 server：
   `/config/uv-constraints-reach.txt`：
   ```
   mcp<2
   playwright==1.65.2
   ```
   在 `config.json` 的 `reach.env` 里设 `UV_CONSTRAINT=/config/uv-constraints-reach.txt`（覆盖全局的 `mcp<2`）。
3. 在 entrypoint `exec uvx mcpo "$@"` 之前加一次 warm（失败不阻塞），并显式用 reach 专用 constraints：
   ```bash
   echo "[mcpo] warming reach uvx env ..."
   UV_CONSTRAINT=/config/uv-constraints-reach.txt \
   uvx --from "reach-mcp[tiktok]==0.7.6" python -c \
     "import reach_mcp; print('reach', reach_mcp.__version__)" \
     || echo "[mcpo] reach warm failed; mcpo will retry"
   ```
4. **第一次升级/换 pin 时，先在维护窗口手工 warm 成功，再重启**：
   ```bash
   docker exec -e UV_CONSTRAINT=/config/uv-constraints-reach.txt mcpo \
     uvx --from "reach-mcp[tiktok]==0.7.6" python -c \
     "import reach_mcp; print(reach_mcp.__version__)"
   ```
   这样 51MB 只下载一次；之后 `uvx` 走缓存。

优点：不改启动命令的结构，能消掉“每次 reach 新版都重下 51MB”。
缺点：第一次 pin/升级仍要付一次下载成本；warm 失败时 mcpo 仍会尝试，可能再次慢。

#### C2（最确定，改动较大）

给 reach 单独建持久 venv，完全绕过 uvx 的每次解析：

```bash
REACH_VENV=/config/reach-venv
REACH_VERSION=0.7.6
if [ ! -x "$REACH_VENV/bin/reach-mcp" ] || \
   ! "$REACH_VENV/bin/python" -c "import reach_mcp; assert reach_mcp.__version__=='$REACH_VERSION'"; then
  uv venv "$REACH_VENV"
  uv pip install --python "$REACH_VENV/bin/python" \
    -c /config/uv-constraints-reach.txt \
    "reach-mcp[tiktok]==$REACH_VERSION"
fi
```

config 里把 command 改成 `/config/reach-venv/bin/reach-mcp`，args 只留 `["--transport","stdio"]`。升级 = 改 `REACH_VERSION` + 重跑一次安装。启动时不再有 uvx 解析/下载。

优点：启动最稳定；缺点：多一个 venv，升级要维护。

#### C3（如果不需要免费 TikTok）

把 `[tiktok]` extra 去掉，直接用 `reach-mcp==0.7.6`：不再下载 51MB Playwright，TikTok 回落到 Apify → OpenCLI → ScrapeCreators。适合“TikTok 不是刚需”的情况。

### 方案 A（目标形态）：移除 last30days server + 把 bird-search vendor 进 reach

**适用前提**：确认不再使用 `/last30days/research`、`/last30days/preflight`、YouTube comments。删除后，Open WebUI 里 last30days 的这两个工具会消失；目前 OWUI/DSH 都没连它，但还要确认 Claude Code/脚本。

改动：

1. **vendor bird-search**（一次性，116KB）：
   ```
   src/reach_mcp/vendor/bird-search/
     bird-search.mjs
     package.json
     LICENSE
     lib/*.js
     lib/*.json
   ```
2. 改 `x.py` 的路径解析，并同步顶部注释（不能再写 “does NOT vendor it”）：
   ```python
   _BIRD_SEARCH_MJS = Path(
       os.environ.get("REACH_MCP_BIRD_SEARCH_MJS")
       or Path(__file__).resolve().parent.parent
       / "vendor" / "bird-search" / "bird-search.mjs"
   )
   ```
3. `pyproject.toml` 加 package-data；**同时加 `MANIFEST.in`**，因为 `publish.yml` 会同时发 sdist，只写 package-data 时 sdist 可能漏 vendor：
   ```toml
   [tool.setuptools.package-data]
   reach_mcp = [
     "vendor/bird-search/*.mjs",
     "vendor/bird-search/*.json",
     "vendor/bird-search/LICENSE",
     "vendor/bird-search/lib/*.js",
     "vendor/bird-search/lib/*.json",
   ]
   ```
   ```
   # MANIFEST.in
   recursive-include src/reach_mcp/vendor/bird-search *
   ```
4. 测试：`pytest -q`；`python -m build` 后同时检查 wheel 和 sdist：
   ```bash
   unzip -l dist/*.whl | grep bird-search
   tar -tzf dist/*.tar.gz | grep bird-search
   ```
   再手工跑一次 `sources=["x"]` 的 live smoke（每会话 1 次）。
5. 发布 `v0.7.7`：bump `pyproject.toml` + `src/reach_mcp/__init__.py`，tag，push（CI 发 PyPI）。
6. **先 warm 再改 config**：
   ```bash
   docker exec -e UV_CONSTRAINT=/config/uv-constraints-reach.txt mcpo \
     uvx --from "reach-mcp[tiktok]==0.7.7" python -c \
     "import reach_mcp; print(reach_mcp.__version__)"
   ```
   warm 成功后才改 config 并重启；否则 reach 子 server 可能整体起不来（不只是 X 降级）。
7. **删 config.json 的 `last30days` 块**（先备份 `config.json.bak-no-last30days-*`），`python3 -m json.tool` 校验。
8. **删 entrypoint 第 1 段**；`/config/last30days` 目录先归档（`tar` 到宿主机），确认 X 正常后再删。
9. 把 reach 的 args 固定到 `reach-mcp[tiktok]==0.7.7`，避免下次 uvx 又拉到未预期版本。
10. **同步文档**：`AGENTS.md` 的「last30days 耦合」「启动慢」两段、`x.py` 顶部注释、本计划的状态行；否则做完后文档会变成假话。

优点：彻底断掉 13MB 下载和 last30days 进程；X 的 bird 路径不再依赖别人的缓存布局。
缺点：要发版；失去 last30days 的 `/research`、`/preflight`、YouTube comments（如果确实在用）。

风险：vendor 的是当前在用的 `bird-search` v0.8.0（基于 2025 年的 `@steipete/bird`）；它只是把现状固化，不解决 X GraphQL 未来漂移。真漂移时升级 `@steipete/bird` 或依赖 cookie fallback。

### 推荐顺序

1. **今天先做 B + C1**：last30days 固定 + reach/playwright 固定 + warm。目标是让 11-19 这种重启 9m→4m，让 11-16 这种 36m→最多一次、之后 4m。
2. 确认 last30days 是否还在用：
   - 不用 → 做 A，进入目标形态；
   - 还在用 → 保持 B，把 `L30D_VERSION` 当普通依赖升级。
3. 如果连 C1 的“第一次 warm”都不想赌，直接上 C2（持久 venv）。
4. **第二阶段**再优化剩下的 3–4 分钟（见 §6），不要和这次混在一起。

---

## 4. 验证与回滚

### 4.1 B 的验证

```bash
docker restart mcpo
docker logs -t --since 10m mcpo | grep -aE '\[last30days\]|Application startup|Successfully connected'
# 期望：要么 "present, skip"，要么没有 downloading；不应再出现 4m39s 的下载
```

### 4.2 C 的验证

```bash
# 版本必须是 pin 的
docker exec mcpo uvx --from "reach-mcp[tiktok]==0.7.6" python -c \
  "import reach_mcp, importlib.metadata as m; print(reach_mcp.__version__, m.version('playwright'))"

# 重启日志里不应再出现 Downloading playwright (51.0MiB)
docker logs -t --since 10m mcpo | grep -a 'Downloading playwright' || echo 'no playwright download'
```

### 4.3 A 的验证

```bash
unzip -l dist/reach_mcp-0.7.7*.whl | grep bird-search
tar -tzf dist/reach_mcp-0.7.7*.tar.gz | grep bird-search

# 容器内路径必须指向 site-packages，而不是 /config/last30days
docker exec mcpo /config/reach-venv/bin/python -c \
  "import reach_mcp.sources.x as x; print(x._BIRD_SEARCH_MJS)"   # 若用 C2
```

### 4.4 回滚（按场景）

- **当前好状态**：`config.json.good-20261119-231023` + `entrypoint.sh.good-20261119-231023`，`docker restart mcpo`。
- **坏 reach venv**：`cat /config/reach-venv.prev` 拿到上一版目录，`ln -sfn <dir> /config/reach-venv`，再 `docker restart mcpo`；或跑 updater `--bootstrap` 重建。
- **只恢复 last30days**：把 `last30days.server.json` 的 `last30days` 块合并进**当前** config，再重启；不要直接覆盖 `config.json.bak-no-last30days-*`（那是旧 uvx/12-server 形态）。当前 entrypoint 不再下载，但现有二进制可启动。
- **完整退回旧形态**：`config.json.bak-no-last30days-*` + `entrypoint.sh.bak-*`，再重启；会重走 uvx/last30days 下载的慢路径，只作最后手段。
- 配置/备份含密钥，统一 `chmod 600`。

---

## 5. 需要你确认的

> 2026-11-19 已确认：last30days 从 config 屏蔽；TikTok 免费后端保留；当前无人使用，已直接实施。

1. **`/last30days/research` 或 `/last30days/preflight` 还在用吗？** OWUI 和 DSH 都没连它；需确认 Claude Code / 脚本 / 其他客户端。
2. **last30days 的 YouTube comments 还在用吗？** reach 目前只取 `comment_count`，不抓评论正文。
3. **TikTok 免费后端（Playwright）是刚需吗？** 不是的话可以走 C3，直接去掉 51MB 的 `[tiktok]` extra。
4. **重启窗口**：`docker restart mcpo` 会中断所有 mcpo 工具约 4 分钟（第一次 warm 可能更久），能否放在没人用的时候？
5. **B 还是 B'**：B 是 pin + 人工升级；B' 是保留自动更新但把下载挪出启动路径（后台下载/宿主机 cron），复杂度更高。默认建议 B。

---

## 6. 第二阶段：剩下的 3–4 分钟（本次不做）

- 12 个 server 是 mcpo **顺序**启动的，单个 5–53s；
- 可选手段：
  - 把 `uvx`/`npx` 的版本全部 pin 死，减少每次解析；
  - 预拉所有 uv/npm 缓存后，用 `UV_OFFLINE=1` / `npm_config_offline=true` 启动；
  - 把 `fetch`、`docling` 这种慢启动的 server 改成预装 venv 直接执行，绕过 uvx 解析；
  - 评估 mcpo 是否支持并发启动（当前日志是串行）。
- 这部分要单独做 A/B 测试，避免“为了快”把某个 server 搞挂。

---

## 7. 附：DSH 迁移

本仓库此前是 Claude Code 形态：

- `.claude/memory/`：20 份项目记忆 + `MEMORY.md` 索引；
- `.claude/remote-global-CLAUDE.md`：firecrawl/codegraph 工具纪律；
- `.claude/settings.local.json`：Claude 专有 permissions；
- **没有 `AGENTS.md`**。

已按兄弟项目（`finance-mcp`、`scientific-data-mcp`）的 DSH 形态迁移：

- 根目录 `AGENTS.md`：唯一常驻指令；
- `docs/memory/`：记忆正文 + `MEMORY.md` 索引；
- `docs/memory/dsh-migration.md`：迁移说明；
- 删除 `.claude/`，不再依赖 Claude hooks/settings；原始目录归档在 `/home/eli/ai-tool/.archive/reach-mcp-claude-20261119/`；
- 新纪律写 `AGENTS.md`，新记忆写 `docs/memory/` 并在索引挂一行。

迁移改动是本地未提交状态，和线上部署无关；可单独 review/commit。

---

## 8. 变更清单（pin 版历史清单）

> 实际执行以 §0 为准：未 pin；last30days 已移除；reach 用持久 venv + 后台最新版更新。


- [ ] B：改 `deploy/entrypoint.sh`（固定 `v4.3.2` + 代理 + fail-open + 预置）
- [ ] B：预置 `last30days-pp-mcp` + `VERSION` 到 `/mnt/docker/mcpserver/last30days/`
- [ ] C1：config pin `reach-mcp[tiktok]==0.7.6`；constraints pin `playwright==1.65.2`
- [ ] C1：维护窗口手工 warm reach，再重启
- [ ] 记录重启耗时；确认日志无 last30days download / Playwright download
- [ ] 决策：A 还是保持 B
- [ ] A：vendor `bird-search` + 改 `x.py` + package-data + `MANIFEST.in` + 测试
- [ ] A：发 `v0.7.7`，先 warm，再改 config/删 last30days 块/entrypoint 第 1 段
- [ ] A：同步 `AGENTS.md`、`x.py` 注释、本计划状态
- [ ] A：验证 X source，归档 `/config/last30days`
- [ ] 第二阶段：单独评估 uvx/npx 启动优化

---

## 9. 评审记录

2026-11-19 独立子代理只读复核，已采纳：

- “279s 是离群值” → 增加历史样本表，不再写“每次 9 分钟”；
- “A 要先 warm 再改 config” → 写进 A 第 6 步；
- “sdist 会漏 vendor” → 增加 `MANIFEST.in`；
- “A 后文档会变假话” → 增加 §8 文档同步项；
- “AGENTS 的版本验证命令会 ModuleNotFoundError” → 改成 uvx warm 命令；
- “源数 33/30/29 不一致” → `AGENTS.md` 数据源段已注明以 `list_sources` 为准；
- “B 的下载失败会被 set -e 终止” → 补丁改为 fail-open；
- “预置必须写 VERSION” → 预置脚本已包含。

未采纳/保留：

- 子代理建议的 B'（保留自动更新、后台下载）作为备选写在 §5，不设为默认；pin 更可预测。
