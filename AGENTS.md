# reach-mcp — 维护指南

多源搜索 MCP：一次查询横跨 33 个中英文信息源，按互动量打分，可选 LLM 重排 + 引用简报。对外 5 个工具：`search`、`list_sources`、`synthesize`、`fetch_content`、`read_url`。

生产形态是 **mcpo 容器里的持久 venv**（`/config/reach-venv`，由 `update-reach-venv.sh` 从 PyPI 最新版安装/更新），不是独立容器，也不是每次启动都走 `uvx` 解析。

本项目由 **DSH 维护**（2026-11-19 从 Claude Code 迁入）。`AGENTS.md` 是唯一常驻指令；`docs/memory/` 是工作记忆，动手前先读 `docs/memory/MEMORY.md`。不再有 `.claude/`、Claude hooks 或 Claude 专有 settings。

## 定位与边界

| 项目 | 管什么 | 不管 |
|------|--------|------|
| **reach-mcp**（本仓库） | 多源关键词检索、热搜/热榜、网页正文抓取、LLM 简报 | 金融行情、科研实体数据、RAG 入库 |
| `last30days` | 旧的闭源同类 MCP；reach 是它的 drop-in 替代 | 2026-11-19 起已从 config 移除；binary/data 保留在 `/config/last30days` 供回滚，reach 不再依赖它 |
| `finance-mcp` | 行情 / 财报 / 宏观 | 社媒与通用网页检索 |
| `scientific-data-mcp` | 化合物 / 蛋白 / 结构 / 文献元数据 | 通用网页检索 |

## 命令

```bash
# 本机沙箱可能挡住默认 uv 缓存，先指到仓库内
export UV_CACHE_DIR=$PWD/.uv-cache UV_PYTHON_INSTALL_DIR=$PWD/.uv-python

uv venv --python 3.12 .venv
uv pip install -e '.[dev]' --python .venv/bin/python

.venv/bin/python -m pytest -q              # hermetic；默认 addopts 已排除 -m real
.venv/bin/python -m pytest -m real -q      # 真实上游 sweep：人工跑，每会话最多 1 次
.venv/bin/ruff check .
.venv/bin/reach-mcp --transport stdio      # mcpo 用这个
python -m build                            # wheel（发布前验证 vendor/package-data）
```

`pytest` 的 `real` 标记会每个源打一次生产端点，凭据缺失的源自动 skip；**不进 CI**，也不要在一次会话里反复跑。

## 架构纪律

- `src/reach_mcp/sources/<name>.py`：一个 `Source` 子类，`register_source` 注册；声明 `name` / `description` / `host` / `needs_auth` / `required_env` / `default_days` / `default_limit`；实现 `fetch()`，热搜源另实现 `fetch_trending()` + `supports_trending = True`。
- `pipeline.py`：`import_all_sources()`、`run_search` / `run_trending`、`CATEGORIES` / `expand_categories()`、打分/去重、`SourceReport`。单源失败折叠进 `source_summary`，不让整次 search 失败。
- `tools.py`：MCP 工具面。`_SEARCH_DESC` 是给模型看的硬约束（query 风格、category、trending、synthesize、凭据 NOTICE），改行为要同步改描述。
- `query_core.py`：按源做 query 改写/降级；`content.py` / `readurl.py`：全文抓取多后端链；`synthesize.py`：rerank + brief；`http.py`：`PoliteClient`。
- **新增源必须同步**：source 模块、`CATEGORIES` 至少一组、`tests/test_sources_coverage.py` 的成员断言、README 源表、`docs/CREDENTIALS.md` 的凭据段；新增 category 还要加 `Category` Literal。漏一处 = 工具面/文档 drift。
- **工具错误**：只有“用户必须看到失败”的路径才 `raise ToolError`（例如 `fetch_content` 完全没内容）。其余失败返回结构化结果 + `source_summary` 里的 `ERRORS`/`NOTICE`，**不要抛异常**。OWUI 的 ✓/✗ 取决于 MCP tool 是否 raise，不取决于 `{ok:false}`。
- **HTTP**：统一走 `http.PoliteClient` / `get_client()`；per-host 限速、429/5xx 重试、超时；不要裸 `httpx`。代理与 `NO_PROXY` 是高频坑，见记忆。
- **不加载 `.env`**：代码只读 `os.environ` / `Settings`；本地用 shell export，生产由 mcpo 的 `config.json` env 注入。不要把真实密钥写进仓库。
- **反幻觉**：只返回上游真实字段；缺失就留空/省略，不推断、不补全；`source_summary` 的 NOTICE 要如实透传。

## 数据源与凭据

- 33 个源（`list_sources` 为准；`pyproject.description` 里的 30、旧笔记里的 29 是历史数字，不要据此判断当前工具面）。`list_sources` 同时给出 `available=false`（缺 `required_env`）。
- 凭据获取步骤在 `docs/CREDENTIALS.md`；README「Configuration」有完整 env 表。
- 常见分组：LLM 网关（`OPENAI_BASE_URL`/`OPENAI_API_KEY`）、Searxng（`SEARXNG_URL`）、Jina、GitHub（`GITHUB_BASE_URL` 或 `GH_TOKEN`）、X（`AUTH_TOKEN`/`CT0`）、Bluesky、Truth Social、Apify、ScrapeCreators、小红书 companion、微博/知乎/头条、雪球、Whisper、Exa/Firecrawl/Tavily（走 key-rotator）。
- `api-key-rotator:8788` 的 `*_BASE_URL` + dummy-key 模式见记忆；新增走 rotator 的服务必须把 host 加进 `NO_PROXY`/`no_proxy`。

## 部署

- 生产：`eli@dockerno1` 的 `mcpo` 容器；宿主目录 `/mnt/docker/mcpserver/`。
  - `config.json`：每个 server 的启动命令与 env（改前备份 `.bak-*`，改后 `python3 -m json.tool` 校验）。
  - `entrypoint.sh`：仓库 `deploy/entrypoint.sh` 是源文件；**改完要同步到宿主**（当前两者 sha256 一致）。
- reach 的启动参数：`/config/reach-venv/bin/reach-mcp --transport stdio`。venv 由 `/config/update-reach-venv.sh` 从 PyPI 最新版安装/更新：启动时先用现有 venv，后台检查新版，安装验证后原子切换 symlink，不阻塞启动。**不 pin 版本**，跟随 PyPI 最新。`[tiktok]` extra 保留；chromium 在 `/config/ms-playwright`（当前 1255）。Playwright 自带 node 缺 `libatomic.so.1`，entrypoint 用 `PLAYWRIGHT_NODEJS_PATH=/usr/bin/node`；容器重建后 entrypoint 会按需 `playwright install-deps chromium` 补系统库。
- `UV_CONSTRAINT=/config/uv-constraints.txt` 固定 `mcp<2`；mcpo 0.0.20 与部分子 server 不兼容 mcp 2.x，**不要删**。
- 缓存都在 `/config` 卷：`uv-cache`、`uv-tools`、`npm-cache`、`bin`、`go`、`ms-playwright`、`reach-venv*`、`reach-bird`。`touch /config/UPGRADE` 会清二进制缓存并重装（last30days 已不启动，不再受它影响）。`config.json` 及 `.bak-*` 含明文密钥，统一 600；不要放宽。
- **回滚**：当前好状态用 `config.json.good-20261119-231023` + `entrypoint.sh.good-20261119-231023`；只恢复 last30days 用 `last30days.server.json` 合并进当前 config（不要直接覆盖旧备份）；坏 venv 用 `cat /config/reach-venv.prev` 指向的旧 venv + restart；完整退回 uvx/12-server 旧形态才用 `config.json.bak-no-last30days-*` + `entrypoint.sh.bak-*`（会重走慢路径）。
- **发布/更新**：bump `pyproject.toml` 的 `version` 和 `src/reach_mcp/__init__.py` 的 `__version__`（必须一致）→ `git tag vX.Y.Z && git push origin main vX.Y.Z` → `.github/workflows/publish.yml` 发 PyPI。GitHub push 本身不会让线上生效。`/config/update-reach-venv.sh` 在容器启动和每天 04:20 的 host cron 检查 PyPI 最新版，装入新 venv 后切 symlink；运行中的 reach 进程仍用旧 venv，**下次 `docker restart mcpo` 才生效**。要立刻生效：`docker exec mcpo /config/update-reach-venv.sh && docker restart mcpo`。单次重启可能仍跑旧版（updater 在 spawn 后才装完），必要时重启两次。
- 验证线上版本：`docker exec mcpo /config/reach-venv/bin/python -c "import reach_mcp, importlib.metadata as m; print(reach_mcp.__version__, m.version('playwright'))"`，再对照 `pypi.org/pypi/reach-mcp/json`。
- **X bird 已 vendored + 运行时缓存**：`src/reach_mcp/vendor/bird-search/`（116KB、16 个文件，MIT，基于 `@steipete/bird` 0.8.0）。`sources/x.py` 默认从包内解析；生产 entrypoint 导出 `REACH_MCP_BIRD_SEARCH_MJS=/config/reach-bird/current/bird-search.mjs`。`/config/update-bird-vendor.sh` 从 last30days upstream 算**目录内容哈希**：不变复用 `/config/reach-bird/current`，变了才下载 tarball 并原子切换；运行中的 reach 进程无需重启，下一次 X 搜索就用新文件。每日 04:25 cron + 启动检查；**无需 GitHub PR / reach 发版**。`scripts/sync_bird_vendor.sh` 只用于手动刷新仓库里的 fallback。不再读 `/config/last30days`。
  - 依赖边界：运行时不依赖 last30days；bird 的**更新源**仍是 `mvanhorn/last30days-skill` 的 GitHub，缓存后不影响启动；如果该仓库消失，现有缓存/包内 fallback 仍可用，只是不再更新。
- **启动慢已处理（2026-11-19）**：last30days 从 config 移除，entrypoint 不再下载；reach 改为持久 venv + 后台最新版更新，避免 uvx 在启动时下载 51MB Playwright。实测重启 **84–149s**（第一次 149s，第二次 84s；原 8m39s / 36m10s 的两个慢样本不再走阻塞路径）。注意：首次 bootstrap venv 仍可能慢一次；后续不阻塞。每日 04:20 host cron 也会跑 updater（`crontab -l`，日志 `/home/eli/logs/reach-update.log`）。

## 测试纪律

- 默认 `pytest -q` 是 hermetic（mock 上游，零 egress）；CI 只跑这个。
- `pytest -m real` 是 live smoke：每个源一次请求，**人工跑**，一次会话最多 1 次；凭据缺失自动 skip。
- Playwright 相关测试必须同时 patch `_playwright_available` 和 `_playwright`，否则 CI（无 playwright）会在 mock 之前 early-return。
- 新增源先写失败测试（TDD），再实现；至少覆盖：可用性门控、正常解析、上游空/错误、query 改写。
- 提交前 `ruff check .`；仓库有 `.pre-commit-config.yaml`，可选用。

## 已知基础设施限制

这些不是代码 bug，别在源实现里“修”：

- 容器出口是数据中心 IP：YouTube 字幕只有 storyboard（永远拿不到可播放格式）；digg API 429；LinkedIn 的 Jina 泛搜常 0。
- 小红书依赖 `xiaohongshu-mcp` companion 已登录；cookie 会过期。
- 知乎搜索依赖 `ZHIHU_COOKIE`；被 WAF 拉黑后连热榜都会 401，搜索应停止而不是降级。
- linux.do 需要 playwright + seeded `LINUXDO_COOKIE`；纯 curl 带 cookie 也 403。
- 详细逐源状态见 `docs/memory/reach-mcp-source-implementation-status.md`。

## 记忆

`docs/memory/MEMORY.md` 是索引。改某个域之前先读对应笔记：

- 改部署 / 发布 / 启动 → `reach-mcp-release-flow.md` + `mcpo-startup-and-last30days.md`
- 改 X / bird / last30days 耦合 → `mcpo-startup-and-last30days.md` + `reach-mcp-source-implementation-status.md`
- 改出口 / 代理 / NO_PROXY → `reach-mcp-container-egress-diagnosis.md` + `reach-mcp-egress-proxy-dns-path.md`
- 改 GitHub 源 → `reach-mcp-github-proxy-backend.md`
- 改 key-rotator / Exa / Firecrawl / Tavily → `key-rotator-gateway-endpoints.md` + `exa-search-capabilities.md`
- 改 category / 工具描述 / 新增源 → `reach-mcp-source-categories.md` + `reach-mcp-source-implementation-status.md`
- 改热搜 → `reach-mcp-trending-mode.md`
- 改中文源（知乎/微博/头条/微信/豆瓣/linux.do） → 对应端点笔记
- 改 Apify / ScrapeCreators → `apify-run-sync-gotchas.md` + `scrapecreators-one-time-credits.md`
- 改 Whisper / 小宇宙 → `reach-mcp-whisper-gateway-behavior.md`
- 迁移背景 / DSH 形态 → `dsh-migration.md`

## Agent 工具纪律

- 取网页 / 搜索走 **firecrawl**（`firecrawl_scrape` / `firecrawl_search`），不用原生 WebFetch；抓正文可加 `onlyCleanContent: true`。
- 仓库根有 `.codegraph/` 时，先用 codegraph（MCP `codegraph_explore` 或 shell `codegraph query`）再 grep/read。
- DSH 只自动加载 `AGENTS.md` / `CLAUDE.md`；新纪律写这里，新记忆写 `docs/memory/` 并在索引挂一行。不要再引入 `.claude/` 依赖。
