# reach-mcp 配置获取指南

按顺序从前往后逐个获取。每条都给出**准确入口 URL + 步骤**。所有值都是可选的——什么都不配,服务器也能跑,只是退化成"纯免费源"模式。**建议从上到下逐步点亮**,每点亮一个源,`list_sources` 里就多一个 `available`。

> 配好后,把值写进你的配置处:
> - **mcpo**:`deploy/mcpo-config.example.json` 的 `reach.env` 块
> - **Docker / uvx**:`.env` 文件或 compose `environment`
> 完整键名见 [README 配置参考](../README.md#configuration)。

---

## 第 0 级 · 核心(强烈建议先配)

### 1. OpenAI 兼容网关(`OPENAI_BASE_URL` + `OPENAI_API_KEY`)

这是唯一影响**主体验**的键:没有它,搜索仍返回原始结果,但**没有 LLM 重排和简报**。

- 需要一个 OpenAI 兼容的 chat completions 网关(任何提供商:OpenAI、本地 vLLM/Ollama、各家转发网关均可)
- `OPENAI_BASE_URL` 是网关 base URL,**不要带** `/v1/responses`(reach-mcp 会自动拼 `/chat/completions`)
- `OPENAI_API_KEY` 是密钥
- 默认模型 `REACH_MCP_RERANK_MODEL` / `REACH_MCP_BRIEF_MODEL` 是 `gemini-flash-lite`——如果你没有 Gemini 网关,记得改成你的提供商支持的模型名

### 2. Searxng(`SEARXNG_URL`)

`web` 源的必需后端(默认 `http://searxng:8080`)。不是 API 键,是一个要跑起来的服务。

- 最省事:`docker compose` 加一个 `searxng/searxng:latest` 服务(参考 [docker-compose.yml](../docker-compose.yml) 底部)
- 或 [searxng 官方文档](https://docs.searxng.org/) 直接部署

---

## 第 1 级 · 免费月度配额(注册即得,每月重置,推荐配)

### 3. Jina(`JINA_API_KEY`) —— 🔓 你目前还没有

免费主后端(LinkedIn 搜索 + `read_url` 工具)。

1. 打开 [jina.ai](https://jina.ai/) 注册
2. 登录后进 [API Keys 页](https://jina.ai/keys/)(Reader API key)
3. 复制 `jina_...` 密钥 → 设 `JINA_API_KEY`

免费 key 是**月度配额**(无 key 时 20 RPM,免费 key 500 RPM,付费 5000 RPM),**不是一次性额度**。`s.jina.ai`(搜索)必须有 key;`r.jina.ai`(读网页)无 key 也能用但限速更低。

### 4. Brave(`BRAVE_API_KEY`) —— `web` 源加速

[brave.com/search/api](https://brave.com/search/api/) 注册,控制台生成 `BSA_...` key。**$5 免费额度/月(每月重置)**,配合 Searxng 并行检索、去重合并。注册即得,无需绑卡。

### 5. Apify(`APIFY_API_TOKEN`) —— threads + tiktok/instagram/pinterest

[apify.com](https://apify.com) 免费计划(**$5 额度/月,月度重置**,够跑数百次搜索)。一个 token 点亮 4 个源:

- `threads` — 唯一可用的免费服务端路径(Meta 官方 API 要应用审核)
- `tiktok` / `instagram` / `pinterest` — 首选后端

1. 注册 → Settings → **Integrations**
2. 复制 `apify_api_...` token → 设 `APIFY_API_TOKEN`

### 6. GitHub(`GH_TOKEN`)

[github.com/settings/tokens](https://github.com/settings/tokens) → 创建 **fine-grained token**,只给 `Public Repositories (read-only)`。不配也能搜,但未认证限速 60 req/hr vs 5000 req/hr。

### 7. Bluesky(`BSKY_HANDLE` + `BSKY_APP_PASSWORD`)

[bsky.app](https://bsky.app) → Settings → **App Passwords** → 新建。app password 是 `xxxx-xxxx-xxxx-xxxx` 格式。不配用公开 API 也能搜,配额更低。

---

## 第 2 级 · 登录态类(从浏览器抓,有风控风险,谨慎)

### 8. X / Twitter(`AUTH_TOKEN` + `CT0`)

1. 登录 x.com → DevTools(F12)→ Application → Cookies → `x.com`
2. 复制 `auth_token` 和 `ct0` 的值
3. 设 `AUTH_TOKEN` / `CT0`

> ⚠️ 建议用**专用小号**;API 式使用可能触发平台反机器人检测。

### 9. Truth Social(`TRUTHSOCIAL_TOKEN`) —— 🔓 你目前还没有

用 Mastodon 兼容 API(bearer token,免费)。

1. 浏览器登录 truthsocial.com
2. DevTools(F12)→ Network 面板 → 找一个发往 `truthsocial.com` 的 API 请求
3. 复制请求头里 `Authorization: Bearer ...` 的值(只要 token 部分)
4. 设 `TRUTHSOCIAL_TOKEN=<bearer token>`

---

## 第 3 级 · 中文源

### 10. 小红书(`XHS_MCP_URL`)—— 需要 companion 服务,不是 key

用社区背书的 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Go 服务器(15K+ star)做后端。`XHS_MCP_URL` 指向它,默认 `http://localhost:18060/mcp`。

**部署(compose 参考 [`docker-compose.yml`](../docker-compose.yml) 底部):**
```yaml
xiaohongshu-mcp:
  image: xpzouying/xiaohongshu-mcp:latest
  ports: ["18060:18060"]
  restart: unless-stopped
  init: true
  tty: true
  volumes:
    - ./data:/app/data        # 必须:cookies + 运行数据持久化
    - ./images:/app/images    # 仅发笔记需要
  environment:
    - COOKIES_PATH=/app/data/cookies.json
    - HOME=/app/data/home
    - XDG_CONFIG_HOME=/app/data/config
```

**扫码登录(一次性,用 MCP Inspector):**
```bash
npx @modelcontextprotocol/inspector
# connect 到 http://localhost:18060/mcp
# 调 `login` 工具 → 出二维码 → 小红书 App 扫码
# 调 `check_login` 确认(必要时再扫一次)
```
注意:先打开 App 再扫(二维码会过期);登录后别在网页端再登同账号(单点登录会踢出 MCP)。

**cookies 存在 `./data` volume**——没挂 volume 则容器重建后登录态丢失,需重新扫码。无需 proxy(国内直连即可);如需要可设 `XHS_PROXY`。

### 11. 小宇宙 + Whisper(`XIAOYUZHOU_ACCESS_TOKEN` + `WHISPER_BASE_URL`) —— 🔓 你目前还没有

小宇宙(xiaoyuzhou)播客搜索 + 转写。

**获取 `XIAOYUZHOU_ACCESS_TOKEN`(普通用户即可,不是主播专属):**

小宇宙搜索 API 需要登录 token(手机短信登录)。任何注册用户都能拿,流程(参照 [xiaoyuzhou-api](https://github.com/ylw1997/xiaoyuzhou-api) 的测试客户端):

```bash
# 1. 发验证码到手机(需已注册小宇宙账号;未注册会报 "该手机号未注册小宇宙")
curl -X POST https://podcaster-api.xiaoyuzhoufm.com/v1/auth/send-code \
  -H "Content-Type: application/json;charset=UTF-8" \
  -d '{"areaCode":"+86","mobilePhoneNumber":"你的手机号"}'

# 2. 用验证码登录 → 响应头里返回 x-jike-access-token + x-jike-refresh-token
curl -X POST https://podcaster-api.xiaoyuzhoufm.com/v1/auth/login-with-sms \
  -H "Content-Type: application/json;charset=UTF-8" \
  -d '{"areaCode":"+86","mobilePhoneNumber":"你的手机号","verifyCode":"收到的验证码"}'
# 从响应头 X-Jike-Access-Token 取值 → 设 XIAOYUZHOU_ACCESS_TOKEN
```

没有注册?打开小宇宙 App 用手机号注册一个即可(免费,普通听众账号就行)。

**转写走 OpenAI 兼容 Whisper**(不再用 Groq):
  1. 默认指向自托管 `WHISPER_BASE_URL=http://gpu.savorcare.com:8080/v1`(LocalAI,模型 `whisper-large`)
  2. `WHISPER_API_KEY` 可空(LocalAI 不校验);`WHISPER_MODEL` 默认 `whisper-large`
  3. 换任意 OpenAI 兼容端点即可(如 Groq 的 `api.groq.com/openai/v1`)
  3. 换任意 OpenAI 兼容端点即可(如 Groq 的 `api.groq.com/openai/v1`)

---

## 第 4 级 · RSS feeds(`RSS_FEEDS`)—— 不是 key,但值得单独推荐

逗号分隔的 feed URL 列表,`rss` 源会按查询在窗口内过滤。**免费、无需注册、立刻可用**——想快速验证 reach-mcp,配一组 RSS 是最低门槛。

### 科技媒体 / 开发社区

```bash
# 全部经 firecrawl 验证可用(返回合法 RSS/Atom)
https://hnrss.org/frontpage,https://lobste.rs/rss,https://techcrunch.com/feed/,\
https://www.theverge.com/rss/index.xml,https://feeds.arstechnica.com/arstechnica/index,\
https://www.wired.com/feed/rss,https://simonwillison.net/atom/everything/,\
https://lwn.net/headlines/rss,https://36kr.com/feed
```

| Feed | 覆盖 | 备注 |
|------|------|------|
| `hnrss.org/frontpage` | Hacker News 首页 | 技术链接信号强 |
| `lobste.rs/rss` | 编程社区精选 | 活跃、质量高 |
| `techcrunch.com/feed/` | 创业/科技新闻 | 约每小时更新 |
| `theverge.com/rss/index.xml` | 消费科技/评测/政策 | Atom,编辑质量高 |
| `feeds.arstechnica.com/arstechnica/index` | 深度科技/安全 | 持续更新 |
| `wired.com/feed/rss` | 科技/科学/文化 | 站点部分文章付费 |
| `simonwillison.net/atom/everything/` | AI/工具深潜博客 | AI 覆盖极佳 |
| `lwn.net/headlines/rss` | Linux 内核/FOSS | 全文付费,标题免费 |
| `36kr.com/feed` | 36氪 中文科技创业 | 中文全文 |

### 财经 / 市场

```bash
https://www.cnbc.com/id/100003114/device/rss/rss.html,\
https://www.cnbc.com/id/10001147/device/rss/rss.html,\
https://feeds.marketwatch.com/marketwatch/topstories/
```

| Feed | 覆盖 | 备注 |
|------|------|------|
| CNBC `id/100003114` | US 头条新闻 | 免费、持续 |
| CNBC `id/10001147` | 商业新闻 | 免费、持续 |
| `feeds.marketwatch.com/marketwatch/topstories/` | 市场/金融头条 | Dow Jones 系,WSJ 免费替代 |

### 政府经济数据 / 政策发布(官方、免费)

```bash
https://www.federalreserve.gov/feeds/press_all.xml,\
https://fredblog.stlouisfed.org/feed,\
https://www.ecb.europa.eu/rss/press.html,\
https://home.treasury.gov/rss.xml
```

| Feed | 覆盖 | 备注 |
|------|------|------|
| `federalreserve.gov/feeds/press_all.xml` | 美联储 FOMC/讲话/法规 | 官方权威,**宏观首选** |
| `fredblog.stlouisfed.org/feed` | 圣路易斯联储 FRED Blog | 经济数据分析+图表,2-3 篇/周 |
| `ecb.europa.eu/rss/press.html` | 欧央行决议/讲话 | 欧元区官方 |
| `home.treasury.gov/rss.xml` | 财政部新闻 | 质量混杂(含 FAQ/项目页) |

> SEC EDGAR 公司公告 feed 也值得单独配(见下文"公司数据")。

### 政治 / 军事新闻

```bash
http://feeds.bbci.co.uk/news/world/rss.xml,\
https://www.aljazeera.com/xml/rss/all.xml,\
https://www.theguardian.com/world/rss,\
https://rss.dw.com/rdf/rss-en-all,\
https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml
```

| Feed | 覆盖 | 备注 |
|------|------|------|
| BBC `news/world/rss.xml` | 全球新闻 | 权威、持续 |
| `aljazeera.com/xml/rss/all.xml` | 世界/中东/政治 | 区域深度 |
| `theguardian.com/world/rss` | 全球新闻 | 持续 |
| `rss.dw.com/rdf/rss-en-all` | 德国之声英文 | 欧洲视角 |
| Defense News | 防务/军事新闻 | 专注军工业 |

### 公司数据 / 财报发布

- **SEC EDGAR**(权威公司公告 feed):
  `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=10-K&output=atom`
  — 按表单类型返回最近 filings(Atom,每查询约 40 条)。⚠️ SEC 要求**声明 HTTP User-Agent**(默认爬虫会被拦),建议用 `reach-mcp (+contact@example.com)` 之类。
- CNBC / MarketWatch(上文)是最好的免费财报聚合。

### 不建议的(付费墙/已死)

| Feed | 原因 |
|------|------|
| Reuters | 2020 年已砍公共 RSS(2026 仍死) |
| Matt Levine / Money Stuff (Bloomberg) | 付费墙,无官方 RSS |
| The Economist / WSJ / Barron's / Seeking Alpha | 付费墙 |
| GlobeNewswire 直接 feed | 400,无可用公开 URL |

---

## 快速核对:你现在缺什么

| 键 | 你目前 | 去哪拿 |
|----|--------|--------|
| `XIAOYUZHOU_ACCESS_TOKEN` | ❌ | 小宇宙手机短信登录(上文第 11 条);`WHISPER_*` 默认已指向自托管,无需注册 |
| `TRUTHSOCIAL_TOKEN` | ❌ | DevTools 抓 bearer(上文第 9 条) |
| `JINA_API_KEY` | ❌ | [jina.ai](https://jina.ai/keys/) |
| `RSS_FEEDS` | 未配 | 上文第 4 级清单,建议先配 `hnrss.org/frontpage` + `federalreserve.gov/feeds/press_all.xml` + `feeds.bbci.co.uk/news/world/rss.xml` 三件套 |
