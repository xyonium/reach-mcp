# mcpo 重启慢：last30days 与 Playwright（2026-11-19 已修复）

`eli@dockerno1` 的 `mcpo` 重启慢有两条版本敏感的下载路径，现在都已从**启动阻塞路径**移走；版本继续跟随上游，不 pin。

**修复前**

- 路径 1：entrypoint 每次查 last30days latest，`VERSION` 不一致就下载 5.8MB `.mcpb`（13,019,258B 二进制）。历史下载 364s / 5s / 49s / 6s / 279s；同版本会 `already at ..., skip`。
- 路径 2：reach 的 `uvx --from "reach-mcp[tiktok]"` 未 pin，`playwright>=1.40` 在新版本时触发 uvx 环境重建，下载 **Playwright 51MB**；2026-11-16 实测 32m10s，总启动 36m10s。
- entrypoint 的 Python `urllib` 直连 GitHub；顶层容器没有代理 env。

**修复后（2026-11-19）**

- last30days 已从 `config.json` 移除：块保存在 `/mnt/docker/mcpserver/last30days.server.json`，二进制/数据保留在 `/config/last30days`；entrypoint 不再下载/不再启动它。last30days 的 `/preflight`、`/research` 不再暴露（reach 的 5 个工具不受影响）。
- reach 改为持久 venv `/config/reach-venv`，由 `/config/update-reach-venv.sh` 从 PyPI 安装**最新版**（不 pin）。启动时用现有 venv；后台检查新版，安装验证后原子切换 symlink，不阻塞重启。首次 bootstrap 可能慢一次。
- 更新边界：updater 只在**容器启动**和**每天 04:20 host cron**（`/home/eli/crontab`，日志 `/home/eli/logs/reach-update.log`）检查；它只更新 venv，运行中的 reach 进程仍用旧版，**下次 restart 才生效**。发版后要立刻生效：`docker exec mcpo /config/update-reach-venv.sh && docker restart mcpo`；单次重启可能仍跑旧版（updater 在 spawn 后才装完），必要时重启两次。
- Playwright 1.65.2 需要 chromium-1255；已补装。自带 driver node 缺 `libatomic.so.1`，entrypoint 用 `PLAYWRIGHT_NODEJS_PATH=/usr/bin/node`，并在容器重建后按需 `playwright install-deps chromium`。
- `reach-mcp 0.7.7` 已把 `bird-search` vendor 进包（`src/reach_mcp/vendor/bird-search`，116KB、16 个文件、MIT、上游 last30days main 同步）；`x.py` 从包内解析，`REACH_MCP_BIRD_SEARCH_MJS` 可覆盖。`scripts/sync_bird_vendor.sh` + `.github/workflows/sync-bird.yml` 每周从上游同步并开 PR。
- 实测：`docker restart mcpo` 到 ready **84–149s**（第一次 149s，第二次 84s；原 8m39s / 36m10s）；11 个 server 全部连上；`/last30days` 404；X 搜索 3–5 条、TikTok 搜索 3 条（Playwright 免费后端正常，无 fallback warning）。
- 安全：`config.json`、`config.json.bak-*`、`last30days.server.json` 含明文密钥，已统一 `chmod 600`；不要放宽。

**How to apply**

- 升级 reach：正常发版 → 等 PyPI 可见 → 立即生效用 `docker exec mcpo /config/update-reach-venv.sh && docker restart mcpo`；否则等每天 04:20 cron 装好，下次 restart 生效。
- 坏 venv 回滚：`cat /config/reach-venv.prev` 拿到上一版目录，`ln -sfn <dir> /config/reach-venv`，再 `docker restart mcpo`；updater 在切换前会写这个文件。
- 只恢复 last30days：把 `last30days.server.json` 的 `last30days` 块合并进**当前** config（不要直接覆盖旧备份），当前 entrypoint 不再下载，但现有二进制可启动；要自动下载旧逻辑才用 `entrypoint.sh.bak-*`。
- 完整退回旧形态（12 server + reach uvx + last30days 下载）：`config.json.bak-no-last30days-*` + `entrypoint.sh.bak-*`；会重走慢路径，只作最后手段。
- 当前好状态备份：`config.json.good-20261119-231023` + `entrypoint.sh.good-20261119-231023`。
- 升级 bird：等每周 workflow 的 PR，或手工 `./scripts/sync_bird_vendor.sh` 后发 reach 版。
- 详细检查/验证命令见 `docs/superpowers/plans/2026-11-19-mcpo-startup-and-last30days.md`。
