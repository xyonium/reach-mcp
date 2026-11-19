# GitHub 源走 research-proxy

`github` 源（src/reach_mcp/sources/github.py）后端优先级：`GITHUB_BASE_URL` → `GH_TOKEN` → 匿名。配 `GITHUB_BASE_URL=http://firecrawl-research-proxy:3100` 时打 `{base}/v2/research/github`（不是 GitHub 原生 `/search/repositories` 路径！直接拼会 404）。返回的 `repo_readme` items 由 `_norm_proxy_item` 规范化；无 stars/created_at（engagement=0），README body 拼进 `text[:4000]`。proxy 失败自动回落直连并在 `last_notice` 标 fallback。

**关键坑**：mcpo 容器 `HTTP_PROXY=192.168.254.253:1090`，`no_proxy` 里 `firecrawl` != `firecrawl-research-proxy`（连字后缀不算前缀）。reach-mcp 打 proxy 会被 192.168.254.253 出口拦成 503（偶发 400 Bad Request——那是 proxy 网关对 query 带 `+` 的反应，`sort=stars` 这种带 + 的参数重试时被拦）。症状 = docker exec 手工 curl 200 但 reach 进程里 503。修法：`/mnt/docker/mcpserver/config.json` 的 `reach` env `NO_PROXY`/`no_proxy` 各加 `firecrawl-research-proxy`（已修）。与 [key-rotator-gateway-endpoints](key-rotator-gateway-endpoints.md) 同型。

memory 补充：research-proxy 源码在 firecrawl 仓库的 **`portainer-stack` 分支**（不在 main）；7 个 GITHUB_TOKENS 跑真实 pool，token 池冷却时会返回 503 `all GitHub tokens cooling down`——不是配置故障，等一下或确认 GitHub 出口 IP 没被杀。

发布 v0.7.3 已上 PyPI + mcpo。
