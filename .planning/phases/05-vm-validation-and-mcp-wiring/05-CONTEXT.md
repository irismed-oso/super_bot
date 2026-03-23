# Phase 5: VM Validation and MCP Wiring - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the mic-transformer MCP server into SuperBot's Claude Agent SDK sessions as a stdio subprocess. Validate all VM prerequisites (credentials, env vars, network access, startup time). Prove end-to-end connectivity with one confirmed tool call through Slack.

</domain>

<decisions>
## Implementation Decisions

### Credential strategy
- Copy config/*.yml files from local dev machine to VM's /home/bot/mic_transformer/config/ via SCP
- SSH access to production server (136.111.85.127) for Prefect tools: unknown, verify during implementation
- Cloud SQL network access (34.136.128.245): unknown, verify firewall rules during implementation
- Env var propagation for MCP subprocess: Claude's discretion (simplest reliable approach)

### Feature flag
- MCP server enabled by default if mic_transformer path exists on disk
- No explicit MIC_TRANSFORMER_MCP_ENABLED env var needed to turn on
- Still provide a way to disable (env var override) for troubleshooting

### Validation method
- Use check_pipeline_status as the proof tool -- broader scope, checks multiple systems
- Test directly via Slack @mention (skip local test script)
- Deploy code, deploy credentials, restart service, then immediately test via Slack

### Startup fallback
- If MCP cold-start exceeds 60-second timeout, use pre-warming approach
- Claude's discretion on implementation (ExecStartPre, separate warm-up script, etc.)
- Benchmark cold-start time on VM first; only implement pre-warming if needed

### Claude's Discretion
- Env var propagation approach (inherit from SuperBot vs separate .env for mic_transformer)
- Pre-warming implementation details (ExecStartPre vs startup script vs other)
- MCP server command/args format in _build_mcp_servers()
- How to handle missing credentials gracefully (warn vs fail)

</decisions>

<specifics>
## Specific Ideas

- The mic_transformer MCP server is at .claude/mcp/mic-transformer/server.py in the mic_transformer repo
- server.py already handles os.chdir(PROJECT_ROOT) and sys.path setup internally
- The .mcp.json config uses: bash -c "source .venv/bin/activate && python .claude/mcp/mic-transformer/server.py" with PYTHONPATH env
- McpStdioServerConfig has no cwd field -- server.py handles this internally (subprocess isolation)
- Only new package needed: mcp[cli]~=1.26.0 in mic_transformer's .venv (NOT standalone fastmcp)

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 05-vm-validation-and-mcp-wiring*
*Context gathered: 2026-03-23*
