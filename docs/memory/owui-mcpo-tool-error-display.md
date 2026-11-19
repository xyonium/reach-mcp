# OWUI / mcpo 的工具错误显示

OpenWebUI calls reach-mcp through mcpo (MCP→OpenAPI bridge). A tool call renders as a green ✓ when the HTTP call returns 200, even if the body is `{..., ok: false}`. It renders a red ✗ only when the call fails.

**Why:** returning a dict with `ok:false` never surfaces as a failure to the UI; an MCP `isError` result does. In FastMCP (mcp 1.x), raising `ToolError` from a tool produces an isError result (mcpo maps it to a non-200 / error the UI marks failed).

**How to apply:** for any MCP tool meant to signal failure to the user (e.g. fetch_content finding no content), raise `ToolError` (or `McpError`) instead of returning `{"ok": False}`. Keep a programmatic `ok` flag only for internal callers (e.g. `_backfill_rich_media` calls the non-raising `content.fetch_content` core). See [reach-mcp-release-flow](reach-mcp-release-flow.md).
