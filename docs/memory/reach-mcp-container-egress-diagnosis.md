# 容器出口诊断：环境变量、代理与数据中心 IP

Diagnosed 2026-08-03 in the mcpo container (`mcp`): the "env not inherited by CLI tools" hypothesis from last30days is **NOT present in reach-mcp**.

**Proof env propagates correctly:**
- reach (PID 284) env contains BOTH `HTTP(S)_PROXY` and lowercase `http(s)_proxy` → `http://192.168.254.253:1090`, plus `YTDLP_COOKIES=/config/youtube_cookies.txt`, `YTDLP_JS_RUNTIMES=node`, `UV_CONSTRAINT`.
- All reach subprocess calls use `asyncio.create_subprocess_exec(...)` **without** `env=` override (grepped `src/reach_mcp/` → NONE) → children inherit parent env.
- Empirically: yt-dlp with empty `YTDLP_PROXY` still logs `Proxy map: {'https': 'http://192.168.254.253:1090', ...}` — it picks up the standard env proxy. digg-pp-cli also reached `di.gg` through it.

**The real blocker is egress type, not env:** all three exits are datacenter IPs:
- HTTP proxy 1090 → 35.236.148.125 (Google Cloud, Taipei)
- socks5 proxy 1091 → 8.208.84.125 (Alibaba Cloud)
- direct (no proxy) → 152.69.204.207

So both proxies are datacenter too — the container route table has no direct route to 192.168.254.0/24 (default via Docker bridge 172.16.0.1), yet hairpinning through the host NAT still reaches the proxies fine (TCP OK on both ports, proxy works for example.com). But YouTube/digg treat all three as datacenter.

**Concrete consequences (verified in container):**
- **digg** → `GET https://di.gg/api/search/stories` returns **429** → CLI falls back to local FTS5 → 0 results. Same as last30days; not a reach bug.
- **YouTube subtitles** → with cookies + proxy, yt-dlp gets past bot-wall to "Downloading subtitles: en" and solves JS challenges with deno, **but then** "Requested format is not available": the android/tv player clients serve only storyboard (`sb0-sb3`) formats to datacenter IPs; forcing `player_client=web` trips captcha. No playable format → subtitle write fails. This is why the container has NEVER succeeded at subtitles.
- **YouTube search** works because `--flat-playlist` hits the search-list endpoint, which passes even under captcha challenge.

**How to apply:** When diagnosing "CLI tool X gets 0 results" in the container, do NOT suspect env loss — it's egress. Fix = residential-IP proxy for youtube subtitles (`YTDLP_PROXY=socks5://<residential>`); digg needs its local FTS5 index built (its live API 429s datacenter IPs regardless). See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md).
