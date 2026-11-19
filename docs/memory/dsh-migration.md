# 从 Claude Code 迁到 DSH

2026-11-19。

## 迁移前

reach-mcp 由 Claude Code 创建，仓库里没有 `AGENTS.md`/`CLAUDE.md`，常驻信息散在：

- `.claude/memory/` —— 20 份项目记忆 + `MEMORY.md` 索引（Claude memory 的 YAML frontmatter 格式）；
- `.claude/remote-global-CLAUDE.md` —— firecrawl 代替 WebFetch、codegraph 优先两条工具纪律；
- `.claude/settings.local.json` —— Claude 专有 permissions（gh / firecrawl）。

`.claude/` 在 `.git/info/exclude` 里，从未进 git；原始目录已归档到
`/home/eli/ai-tool/.archive/reach-mcp-claude-20261119/`。

## 迁移后

- 常驻指令：根目录 **`AGENTS.md`**，是唯一常驻指令。DSH 会加载 `AGENTS.md`/`CLAUDE.md`，本项目只保留 `AGENTS.md`，不建 `CLAUDE.md`，避免两份漂移。
- 记忆：`docs/memory/` + `MEMORY.md` 索引，由 `AGENTS.md` 按域指路。原因：DSH 没有 Claude Code 那种自动 memory 注入，笔记必须显式落库并被指令引用。
- 工具纪律：firecrawl / codegraph 两条从 `remote-global-CLAUDE.md` 搬进 `AGENTS.md` 的「Agent 工具纪律」。
- 未迁移：`.claude/settings.local.json` 的 permissions（Claude 专有；DSH 用沙箱与审批）。
- 记忆正文去掉了 Claude 的 YAML frontmatter，补了中文标题；`[[slug]]` wikilink 转成了相对 Markdown 链接（只转能对应到现有文件的）。
- `docs/superpowers/plans/` 保留本次 mcpo 启动方案的评审文档。

## 以后

- 别再引入 `.claude/`、Claude hooks、Claude 专有 settings。
- 新纪律写 `AGENTS.md`；新记忆写 `docs/memory/` 并在 `MEMORY.md` 挂一行。
- 与 `finance-mcp`、`scientific-data-mcp` 保持同一 DSH 形态，便于跨仓库切换。
