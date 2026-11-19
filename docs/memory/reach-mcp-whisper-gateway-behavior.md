# Whisper 网关行为

The whisper gateway at `WHISPER_BASE_URL` (gpu.savorcare.com:8080, LocalAI) is NOT bound by OpenAI's 25MB hosted-API cap. Measured 2026-08-03: 50.4MB/60min audio transcribed in ~137s, 86.4MB/120min in ~371s (both HTTP 200, verbose_json). Reach's xiaoyuzhou source therefore skips compression/ffmpeg entirely and caps uploads at `_MAX_AUDIO_BYTES = 90MB`; `_TRANSCRIBE_TIMEOUT = 900s` and pipeline `_SLOW_SOURCE_TIMEOUTS = {"xiaoyuzhou": 960}` keep the wrapper from killing long episodes.

**Why:** the first version cargo-culted OpenAI's 25MB limit and a 90s wrapper timeout — real podcast episodes (tens of MB, minutes of GPU time) silently failed. Also: the gateway returns verbose_json `{"segments":[...]}`, not `{"text":...}` — whisper.transcribe must parse segments or every transcription returns "".

**How to apply:** if xiaoyuzhou returns empty text, check (1) gateway reachable, (2) the response format parsing, (3) audio >90MB is intentionally skipped. cliproxy's /v1/audio/speech (tts-hd, zh-CN-YunxiaNeural) exists for TTS but needs an API key that isn't in this repo's env. See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md).
