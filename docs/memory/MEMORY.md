# 项目记忆索引

> 从 Claude Code 的 per-project memory 迁移而来（2026-11-19，源：`.claude/memory/`；原始目录归档在 `/home/eli/ai-tool/.archive/reach-mcp-claude-20261119/`）。
> DSH 不会自动加载 `docs/memory/`，所以这里的笔记由根目录 `AGENTS.md` 显式指路；改对应域之前先读。

## 部署 / 运维

- [发布与部署流程](reach-mcp-release-flow.md) — mcpo + uvx 从 PyPI 拉包；release = bump 两处版本 + 打 `v*` tag；GitHub push 不等于线上生效
- [mcpo 重启慢：last30days 与 Playwright](mcpo-startup-and-last30days.md) — 已修复（2026-11-19）：last30days 移除、reach 改持久 venv + 后台跟随 PyPI 最新、bird 已 vendor；实测重启 149s，X/TikTok 正常
- [容器出口诊断](reach-mcp-container-egress-diagnosis.md) — env 会传给 CLI 子进程；真正限制是代理/直连都是数据中心 IP
- [出口代理与 DNS 解析路径](reach-mcp-egress-proxy-dns-path.md) — `HTTP_PROXY` vs `NO_PROXY` 的差异是 DNS 在哪端解析；arxiv 必须进 NO_PROXY
- [GitHub 源走 research-proxy](reach-mcp-github-proxy-backend.md) — `GITHUB_BASE_URL` 优先于 `GH_TOKEN`；`NO_PROXY` 要含 `firecrawl-research-proxy`
- [OWUI / mcpo 的工具错误显示](owui-mcpo-tool-error-display.md) — UI 的 ✓/✗ 取决于 MCP tool 是否 raise，不是 `{ok:false}`
- [key-rotator 网关端点](key-rotator-gateway-endpoints.md) — exa / firecrawl / tavily 的 `*_BASE_URL` + dummy-key 模式；rotator 要进 NO_PROXY

## 源 / 后端

- [各源实现状态](reach-mcp-source-implementation-status.md) — 哪些源真实可用、哪些是平台/基础设施限制；排“0 结果”先看这里
- [源分类（category）维护](reach-mcp-source-categories.md) — `pipeline.py::CATEGORIES`、`tools.py` 描述、README 三处必须同步
- [热搜 / 热榜模式](reach-mcp-trending-mode.md) — `search(trending=true)` 的源列表与新增方式
- [源后端优先级规则](source-backend-priority-rule.md) — 服务端 headless 优先；OpenCLI 只能做 boost；bili/techmeme/digg CLI 可做 primary
- [知乎 / 微博 / 头条 / 微信端点验证](zhihu-weibo-toutiao-wechat-endpoints-verified.md) — 四个中文源的真实入口与 cookie 行为
- [知乎 api/v4 登录墙](zhihu-api-v4-login-wall.md) — 问答全文走 api/v4 + cookie；专栏文章无服务端全文路径
- [头条端点验证](toutiao-endpoints-verified.md) — 热榜 JSON 免 key；搜索 SSR 不能带 Referer
- [linux.do 的 Playwright + Cookie 后端](linuxdo-playwright-cookie-backend.md) — CF 只认 playwright + seeded cookie；纯 curl 带 cookie 也 403
- [中文平台抓取工具评估](external-cn-scraper-tools-evaluated.md) — TikTok in-page fetch 可用；豆瓣 rexxar 可用；大众点评/知识星球不可用
- [Apify 替代与 IT 源缺口调研](apify-replacement-and-it-gap-research.md) — Stack Overflow / Lobste.rs 免 key 可用；threads playwright 是免费路径
- [Apify run-sync 接口的坑](apify-run-sync-gotchas.md) — tilde actor、2xx 都算成功、180s 超时
- [Exa 搜索能力与配额](exa-search-capabilities.md) — includeDomains + highlights；付费，只作增强层
- [ScrapeCreators 一次性额度](scrapecreators-one-time-credits.md) — 100 credits 一次性，不是每月；LinkedIn 优先 Jina
- [Whisper 网关行为](reach-mcp-whisper-gateway-behavior.md) — 自托管网关无 25MB 限制；verbose_json 要解析 segments

## DSH

- [从 Claude Code 迁到 DSH](dsh-migration.md) — 迁了什么、丢弃了什么、以后别再引入 `.claude` 依赖

## 计划 / 立项

- [mcpo 启动慢：last30days + Playwright 方案](../superpowers/plans/2026-11-19-mcpo-startup-and-last30days.md) — 已实施（2026-11-19）；含历史样本、实际改动、验证与回滚；不 pin 版本
