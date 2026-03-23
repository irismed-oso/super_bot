# Technology Stack

**Project:** SuperBot v1.2 MCP Parity
**Researched:** 2026-03-23
**Scope:** Additions needed to wire mic-transformer MCP server into SuperBot's Claude Agent SDK sessions

---

## Existing Stack (NOT re-researched)

Already validated and running in production (v1.0/v1.1):

| Technology | Version | Purpose |
|------------|---------|---------|
| `claude-agent-sdk` | 0.1.49 | Claude Code agent engine with `mcp_servers` support |
| `slack-bolt` | 1.27.0 | Slack event handling (Socket Mode) |
| `mcp` (Python SDK) | 1.26.0 | MCP protocol (dependency of claude-agent-sdk in super_bot venv) |
| Python | 3.10+ | Runtime on VM |
| systemd | OS-provided | Process management |
| Linear MCP, Sentry MCP | via npx | Already configured in `_build_mcp_servers()` |

---

## New Stack for v1.2

### mic-transformer MCP Server Dependencies

These go in **mic_transformer's .venv** (NOT super_bot's venv). The server subprocess runs with mic_transformer's Python interpreter.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `mcp[cli]` | >=1.0.0, pin to ~=1.26.0 | MCP Python SDK with FastMCP bundled | The server imports `from mcp.server.fastmcp import FastMCP`. FastMCP 1.0 is bundled inside the `mcp` package (not the standalone `fastmcp` PyPI package). The `[cli]` extra adds the `mcp` CLI entry point used by `server.run()`. Pin to 1.26.x for compatibility with the claude-agent-sdk 0.1.49 that SuperBot runs. |

**Do NOT install the standalone `fastmcp` package** (PyPI: `fastmcp>=2.0`). That is a separate project by Prefect/jlowin. The mic-transformer server uses `from mcp.server.fastmcp import FastMCP` which is the version bundled in the official `mcp` SDK package. Installing standalone `fastmcp` would be unused and could cause import confusion.

### No Changes to SuperBot's Own Stack

SuperBot already has `mcp==1.26.0` as a dependency of `claude-agent-sdk`. No new packages needed in super_bot's venv. The MCP server runs as a separate subprocess using mic_transformer's Python.

---

## ClaudeAgentOptions.mcp_servers Config Format

### Type Definition (from claude-agent-sdk 0.1.49)

```python
class McpStdioServerConfig(TypedDict):
    """MCP stdio server configuration."""
    type: NotRequired[Literal["stdio"]]  # Optional for backwards compatibility
    command: str
    args: NotRequired[list[str]]
    env: NotRequired[dict[str, str]]
    # NOTE: No `cwd` field exists. The server must handle its own working directory.
```

The `mcp_servers` parameter on `ClaudeAgentOptions` accepts `dict[str, McpServerConfig]` where keys are server names and values are config dicts.

### Current Config in agent.py (Already Correct)

```python
servers["mic-transformer"] = {
    "command": mcp_python,       # /home/bot/mic_transformer/.venv/bin/python
    "args": [mcp_server_script], # /home/bot/mic_transformer/.claude/mcp/mic-transformer/server.py
}
```

This is already wired in `_build_mcp_servers()` at `bot/agent.py:43-56`. The config:
- Uses mic_transformer's venv Python as the command
- Passes the server.py path as the sole arg
- Does NOT need `cwd` because server.py calls `os.chdir(PROJECT_ROOT)` internally
- Does NOT need `env` because the tools use hardcoded API URLs and SSH for Prefect

### How the SDK Passes Config to Claude CLI

The SDK serializes the dict to JSON and passes it as `--mcp-config '{"mcpServers": {...}}'` to the underlying Claude CLI process. For stdio servers, Claude CLI spawns the subprocess directly. The server communicates via stdin/stdout using the MCP stdio protocol.

### Optional: Adding env for MIC_TRANSFORMER_API_URL

If the API URL needs to differ on the VM (unlikely since tools hardcode `136.111.85.127:8080`):

```python
servers["mic-transformer"] = {
    "command": mcp_python,
    "args": [mcp_server_script],
    "env": {"MIC_TRANSFORMER_API_URL": "http://136.111.85.127:8080"},
}
```

The `env` dict in `McpStdioServerConfig` is passed to the subprocess environment. Use this only if you need to override the default API URL.

---

## What mic-transformer's .venv Needs on the VM

### Required Python Packages

The MCP server subprocess needs these in `/home/bot/mic_transformer/.venv`:

| Package | Why Needed |
|---------|-----------|
| `mcp[cli]~=1.26.0` | Core MCP server framework (`from mcp.server.fastmcp import FastMCP`, `server.run()`) |
| `requests` | HTTP calls to mic-transformer API, Prefect API, Google Drive |
| All existing mic_transformer deps | Storage tools import `from lib.models.S3Remits import S3Remits` etc. |

The server.py adds `PROJECT_ROOT` and `PROJECT_ROOT/lib` to `sys.path`, so the full mic_transformer project dependencies must be installed.

### Installation on VM

```bash
# Activate mic_transformer's venv (NOT super_bot's)
source /home/bot/mic_transformer/.venv/bin/activate

# Install MCP SDK (the only NEW dependency)
pip install "mcp[cli]~=1.26.0"

# Verify
python -c "from mcp.server.fastmcp import FastMCP; print('OK')"
```

### Credentials Already on VM (No New Config)

The MCP tools use these credentials, which should already be available on the VM:

| Credential | How Used | How Available |
|------------|----------|---------------|
| AWS credentials | S3 storage access (`S3Remits` model) | `~/.aws/credentials` or instance profile |
| GCS service account | Google Cloud Storage access | `GOOGLE_APPLICATION_CREDENTIALS` env var |
| SSH key for Prefect host | `ssh ansible@136.111.85.127` for journalctl | `~/.ssh/` key |
| Google Drive service account | Drive folder audit | Service account JSON in mic_transformer config |

---

## Subprocess Lifecycle

### How Claude CLI Manages MCP Server Subprocesses

1. SuperBot calls `claude_agent_sdk.query()` with `mcp_servers={"mic-transformer": {...}}`
2. SDK spawns Claude CLI with `--mcp-config '{"mcpServers": {"mic-transformer": {"command": "...", "args": [...]}}}'`
3. Claude CLI spawns the MCP server as a stdio subprocess at session start
4. Claude calls MCP tools via stdin/stdout JSON-RPC during the session
5. Claude CLI kills the MCP subprocess when the session ends

The MCP server lives for the duration of a single `query()` call (one Slack message processing). It is spawned fresh each time. There is no persistent MCP server process.

### Implications

- **No long-running process management needed** -- Claude CLI handles subprocess lifecycle
- **Cold start per message** -- server.py imports and `os.chdir()` on every invocation. With mic_transformer's large dependency tree, this may add 2-5 seconds of startup. Acceptable for a Slack bot (users expect some latency).
- **Crash isolation** -- if the MCP server crashes, it only affects the current session. Next message spawns a fresh one.

---

## What NOT to Add

| Avoid | Why |
|-------|-----|
| Standalone `fastmcp` PyPI package | Different project from `mcp.server.fastmcp`. Would be unused, wastes space, risks import shadowing. |
| `mcp` package in super_bot's venv | Already there as a dependency of `claude-agent-sdk`. No action needed. |
| Custom subprocess management for MCP server | Claude CLI handles spawning/killing. Do not wrap in your own `Popen`. |
| `cwd` in mcp_servers config | `McpStdioServerConfig` does not have a `cwd` field. The server handles this internally via `os.chdir(PROJECT_ROOT)`. |
| HTTP/SSE transport for mic-transformer MCP | stdio is simpler, lower latency, no port management. HTTP/SSE only needed for remote MCP servers. |
| Environment variable passthrough for most tools | Tools hardcode API URLs and credentials paths. Only `MIC_TRANSFORMER_API_URL` is configurable via env, and the default is correct. |
| New config.py variables | The current `_build_mcp_servers()` already reads `MIC_TRANSFORMER_CWD` from env to find the server script. No new config needed. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| MCP package | `mcp[cli]~=1.26.0` | Standalone `fastmcp>=3.0` | The server already uses `from mcp.server.fastmcp import FastMCP` (bundled FastMCP 1.0 in `mcp` package). Switching to standalone FastMCP 3.x would require rewriting all tool registrations. |
| Transport | stdio (current) | HTTP/SSE server | Adds port management, health checks, firewall rules. stdio is local-only, zero config, managed by Claude CLI. |
| MCP version pinning | `~=1.26.0` (compatible release) | `>=1.0.0` (loose) | Loose pinning risks breaking changes. The `mcp` package has had breaking API changes between major versions. Pin to what super_bot's claude-agent-sdk depends on. |
| Server process model | Per-session (Claude CLI manages) | Long-running daemon | Would need systemd unit, health checks, restart logic. Per-session is simpler, crash-isolated, and adequate for Slack bot latency. |

---

## Version Compatibility Matrix

| Component | Version | Constraint Source |
|-----------|---------|-------------------|
| `claude-agent-sdk` (super_bot) | 0.1.49 | Depends on `mcp` -- drives version alignment |
| `mcp` (super_bot, transitive) | 1.26.0 | Installed by claude-agent-sdk |
| `mcp[cli]` (mic_transformer) | ~=1.26.0 | Must be compatible with CLI that claude-agent-sdk bundles |
| Python (mic_transformer) | 3.10 | Existing venv on VM |
| Python (super_bot) | 3.10 | Existing venv on VM |
| `server.py` import | `from mcp.server.fastmcp import FastMCP` | Requires `mcp>=1.0.0` (FastMCP 1.0 bundled) |
| `server.run()` | stdio transport | Default for `FastMCP.run()` when invoked as subprocess |

---

## Sources

- `mcp` PyPI package -- version 1.26.0, includes `mcp.server.fastmcp`: https://pypi.org/project/mcp/
- `fastmcp` PyPI package (standalone, NOT used) -- version 3.1.1: https://pypi.org/project/fastmcp/
- `claude-agent-sdk` PyPI -- version 0.1.49: https://pypi.org/project/claude-agent-sdk/
- `McpStdioServerConfig` type definition: verified from `claude_agent_sdk/types.py` line 498-504 in installed package
- `_build_mcp_servers()` implementation: verified from `bot/agent.py` lines 43-78
- mic-transformer MCP server: verified from `.claude/mcp/mic-transformer/server.py` and `requirements.txt`
- MCP Python SDK GitHub: https://github.com/modelcontextprotocol/python-sdk

---
*Stack research for: SuperBot v1.2 MCP Parity -- mic-transformer MCP integration*
*Researched: 2026-03-23*
