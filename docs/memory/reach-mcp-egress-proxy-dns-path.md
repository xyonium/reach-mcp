# 出口代理与 DNS 解析路径

reach-mcp/mcpo 里 HTTP_PROXY=192.168.254.253:1090。用户常以为"proxy vs direct 都走同一台 254.253 出口，只是 passwall 分流规则不同"——**不是**。本质差别在 DNS 解析发生的位置：

- **带 HTTP_PROXY (httpx 默认 trust_env=True 捡起)**: httpx 发 `CONNECT host:port`，域名由 proxy 服务器在自己本地 DNS 里解析。那台 proxy 的 DNS 上游对 fastly.ly / export.arxiv.org 给出被污染或老 IP → 握到 Fastly 时被 ACK → RST → `ConnectError`.
- **NO_PROXY 列出该 host**: 容器自己调 `getaddrinfo`,走 docker-gw → host DNS → 局域网网关转发解析，得到 Fastly 正常 IP,TLS 直接通。

症状：同一托管代码在 firecrawl-research-proxy（无 HTTP_PROXY env）打 export.arxiv.org 200 OK；在 mcpo+reach（有 HTTP_PROXY）打同样 endpoint ConnectError。这不是 passwall 规则缺项，是 **DNS 解析路径分叉**——一类 host 把 fastly 当成高价值目标做了封锁/污染。

**修法**（已做）: `/mnt/docker/mcpserver/config.json` 的 reach env `NO_PROXY`/`no_proxy` 把 `export.arxiv.org,arxiv.org` 加进去。future hosts needing host-DNS resolution go in the same list (firecrawl-research-proxy、key-rotator 模式同型)。**不要**在 192.168.254.253 上去加 export 规则——问题不是"没代"，是"被代 + proxy 自己的 DNS"。

[火焰坑兄弟]: github 源 GITHUB_BASE_URL=firecrawl-research-proxy 也是 NO_PROXY 必须含该 internal hostname——见 [reach-mcp-github-proxy-backend](reach-mcp-github-proxy-backend.md)。
