# mcpo 重启慢：last30days 与 Playwright（2026-11-19 已修复）

`eli@dockerno1` 的 `mcpo` 重启慢有两条版本敏感的下载路径，现在都已从**启动阻塞路径**移走；版本继续跟随上游，不 pin。

**修复前**

- 路径 1：entrypoint 每次查 last30days latest，`VERSION` 不一致就下载 5.8MB `.mcpb`（13,019,258B 二进制）。历史下载 364s / 5s / 49s / 6s / 279s；同版本会 `already at ..., skip`。
- 路径 2：reach 的 `uvx --from "reach-mcp[tiktok]"` 未 pin，`playwright>=1.40` 在新版本时触发 uvx 环境重建，下载 **Playwright 51MB**；2026-11-16 实测 32m10s，总启动 36m10s。
- entrypoint 的 Python `urllib` 直连 GitHub；顶层容器没有代理 env。

**修复后（2026-11-19）**

- last30days 已从 `config.json` 移除：块保存在 `/mnt/docker/mcpserver/last30days.server.json`，二进制/数据保留在 `/config/last30days`；entrypoint 不再下载/不再启动它。last30days 的 `/preflight`、`/research` 不再暴露（reach 的 5 个工具不受影响）。
- reach 改为持久 venv `/config/reach-venv`，由 `/config/update-reach-venv.sh` 从 PyPI 安装**最新版**（不 pin）。启动时用现有 venv；后台检查新版，安装验证后原子切换 symlink，不阻塞重启。首次 bootstrap 可能慢一次。
- Playwright 1.65.2 需要 chromium-1255；已补装。自带 driver node 缺 `libatomic.so.1`，entrypoint 用 `PLAYWRIGHT_NODEJS_PATH=/usr/bin/node`，并在容器重建后按需 `playwright install-deps chromium`。
- `reach-mcp 0.7.7` 已把 `bird-search` vendor 进包（`src/reach_mcp/vendor/bird-search`，116KB、MIT、上游 last30days main 同步）；`x.py` 从包内解析，`REACH_MCP_BIRD_SEARCH_MJS` 可覆盖。`scripts/sync_bird_vendor.sh` + `.github/workflows/sync-bird.yml` 每周从上游同步并开 PR。
- 实测：`docker restart mcpo` 到 ready **84–149s**（第一次 149s，第二次 84s；原 8m39s / 36m10s）；11 个 server 全部连上；`/last30days` 404；X 搜索 3–5 条、TikTok 搜索 3 条（Playwright 免费后端正常，无 fallback warning）。

**How to apply**

- 升级 reach：正常发版即可，venv updater 会在后台发现最新版；要立刻生效就重启 mcpo。
- 回滚 last30days：恢复 `config.json.bak-no-last30days-*` 和 `last30days.server.json`；entrypoint 第 1 段已删，需要手工恢复下载逻辑或直接使用现有二进制。
- 升级 bird：等每周 workflow 的 PR，或手工 `./scripts/sync_bird_vendor.sh` 后发 reach 版。
- 详细检查/验证命令见 `docs/superpowers/plans/2026-11-19-mcpo-startup-and-last30days.md`。
