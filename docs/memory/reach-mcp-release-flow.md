# 发布与部署流程

reach-mcp production deploy is **mcpo (the `mcpo` container) → persistent venv `/config/reach-venv` → PyPI latest**. There is NO standalone reach-mcp container in the fleet; the repo Dockerfile/ghcr image is published but unused.

> 2026-11-19 起不再用 `uvx --from ...` 每次启动解析，也不 pin 版本。`/config/update-reach-venv.sh` 从 PyPI 安装最新版：启动时先用现有 venv，后台检查新版，安装验证后原子切换 symlink，不阻塞重启。last30days 已从 config 移除，entrypoint 不再下载它；详见 [mcpo-startup-and-last30days](mcpo-startup-and-last30days.md)。

**Release checklist：**
1. Bump `version` in pyproject.toml AND `__version__` in `src/reach_mcp/__init__.py` (they must match the tag or PyPI rejects the duplicate).
2. `git tag v0.X.Y && git push origin main v0.X.Y` → `.github/workflows/publish.yml` (Trusted Publisher, id-token) builds and uploads. ~40s.
3. Activate: wait for PyPI to show the new version, then either
   - `docker exec mcpo /config/update-reach-venv.sh`（同步安装并切 symlink），再 `docker restart mcpo`；或
   - 直接 `docker restart mcpo`，entrypoint 先用现有 venv、后台 updater 再切新版（下次 spawn 生效）。
   已运行的 reach 进程保持旧 venv，直到 mcpo 重启。
4. Verify: `docker exec mcpo /config/reach-venv/bin/python -c "import reach_mcp; print(reach_mcp.__version__)"` + `list_sources()` count（当前 33）。

**Deploy files (host):**
- config `/mnt/docker/mcpserver/config.json`（reach.command = `/config/reach-venv/bin/reach-mcp`，args `["--transport","stdio"]`；备份 `.bak-*`）。
- entrypoint `/mnt/docker/mcpserver/entrypoint.sh`（repo `deploy/entrypoint.sh` — copy after edits）。
- updater `/mnt/docker/mcpserver/update-reach-venv.sh`（repo `deploy/update-reach-venv.sh`）。
- venv `/config/reach-venv`（symlink 到 `/config/reach-venv-<version>-<ts>`；保留旧版以便回滚）。
- caches `/config/uv-cache`、`/config/uv-tools`、`/config/npm-cache`、`/config/bin`、`/config/go`、`/config/ms-playwright`。

**last30days 回滚：** 块在 `/mnt/docker/mcpserver/last30days.server.json`；恢复 config/entrypoint 备份并重启。二进制/数据仍在 `/config/last30days`，没有删除。

**CI gotcha:** tests run on CI WITHOUT playwright installed — lifecycle tests must patch `_playwright_available` AND `_playwright`, else the early return skips the browser mock entirely (broke v0.4.0's CI).

GitHub repo About updated via `gh repo edit xyonium/reach-mcp --description "..."`.

**How to apply:** never assume a git push changed production; check `pypi.org/pypi/reach-mcp/json` vs `/config/reach-venv/bin/python -c "import reach_mcp; print(reach_mcp.__version__)"`. See [external-cn-scraper-tools-evaluated](external-cn-scraper-tools-evaluated.md) for the tiktok/douban context.
