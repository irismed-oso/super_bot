# Architecture Research: mic-transformer MCP Integration

**Domain:** MCP server integration into existing Claude Agent SDK architecture
**Researched:** 2026-03-23
**Confidence:** HIGH (primary sources: Claude Agent SDK source code in installed package, mic-transformer server.py source, Claude Code MCP docs)
**Mode:** Integration architecture for v1.2 MCP Parity milestone

## Integration Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           GCP VM                                     │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  SuperBot (bot/agent.py)                                    │      │
│  │  ClaudeAgentOptions(mcp_servers={...})                      │      │
│  └──────────┬─────────────────────────────────────────────────┘      │
│             │ spawns Claude CLI subprocess                           │
│             ▼                                                        │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  Claude Code CLI                                            │      │
│  │  Receives --mcp-config JSON with server definitions         │      │
│  │                                                              │      │
│  │  Spawns MCP server subprocesses:                            │      │
│  │  ┌─────────────────────────────────────────────────┐        │      │
│  │  │  mic-transformer MCP (stdio)                     │        │      │
│  │  │  cmd: /home/bot/mic_transformer/.venv/bin/python │        │      │
│  │  │  arg: .claude/mcp/mic-transformer/server.py      │        │      │
│  │  │  env: {inherited + explicit env vars}            │        │      │
│  │  │                                                   │        │      │
│  │  │  server.py does:                                  │        │      │
│  │  │  1. sys.path.insert(PROJECT_ROOT)                │        │      │
│  │  │  2. sys.path.insert(PROJECT_ROOT/lib)            │        │      │
│  │  │  3. os.chdir(PROJECT_ROOT)  ← CRITICAL          │        │      │
│  │  │  4. FastMCP("mic-transformer").run()             │        │      │
│  │  └─────────────────────────────────────────────────┘        │      │
│  │                                                              │      │
│  │  ┌─────────────────────────┐ ┌────────────────────────┐    │      │
│  │  │ linear MCP (npx stdio) │ │ sentry MCP (npx stdio) │    │      │
│  │  └─────────────────────────┘ └────────────────────────┘    │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  /home/bot/mic_transformer/                                │      │
│  │  ├── .venv/bin/python          (MCP subprocess interpreter)│      │
│  │  ├── .claude/mcp/mic-transformer/server.py                 │      │
│  │  ├── config/*.yml              (DB creds, GCS creds, etc.) │      │
│  │  ├── lib/                      (shared libraries)          │      │
│  │  └── .env                      (env vars, NOT auto-loaded) │      │
│  └────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
```

## Component Analysis

### Existing Components (No Modification Needed)

| Component | Why No Changes |
|-----------|---------------|
| `bot/app.py` | Slack event handling unchanged |
| `bot/handlers.py` | Task dispatch unchanged |
| `bot/queue_manager.py` | Queue serialization unchanged |
| `bot/worktree.py` | Git worktree management unchanged |
| `bot/progress.py` | Progress reporting unchanged |

### Components Requiring Modification

| Component | Change | Reason |
|-----------|--------|--------|
| `bot/agent.py` `_build_mcp_servers()` | Add `env` dict to mic-transformer server config | MCP subprocess needs credentials passed via env vars |
| `config.py` | Add mic-transformer credential env var mappings | New env vars for DB, GCS, API credentials |

### New Components

None required. The existing `_build_mcp_servers()` pattern already supports the mic-transformer server -- it just needs the `env` field populated.

## Key Technical Questions Answered

### 1. Does Claude Agent SDK's `mcp_servers` support a `cwd` field?

**Answer: NO, and it is NOT needed.**

The `McpStdioServerConfig` TypedDict (verified in installed SDK at `claude_agent_sdk/types.py` lines 498-504) supports exactly three fields:

```python
class McpStdioServerConfig(TypedDict):
    type: NotRequired[Literal["stdio"]]
    command: str
    args: NotRequired[list[str]]
    env: NotRequired[dict[str, str]]
```

No `cwd` field exists. However, this is irrelevant because `server.py` already handles working directory internally via `os.chdir(PROJECT_ROOT)` on line 28. The `PROJECT_ROOT` is computed from `__file__` using `os.path.dirname()` chain, so it works regardless of where the subprocess is spawned from.

**Confidence: HIGH** -- verified directly in installed SDK source code.

### 2. How does `os.chdir()` in server.py interact with SuperBot's process?

**Answer: No conflict. The MCP server runs as a separate subprocess.**

The execution chain is:
1. SuperBot (bot/agent.py) calls `query()` with `ClaudeAgentOptions`
2. The SDK spawns the **Claude CLI** as a subprocess (verified in `subprocess_cli.py`)
3. The Claude CLI spawns each MCP server as **its own subprocess**
4. `server.py`'s `os.chdir()` only affects the MCP server's subprocess -- not the Claude CLI, not SuperBot

Therefore `os.chdir(PROJECT_ROOT)` in server.py is safe and desirable. It ensures relative paths in config YAML files (`config/db_irismedapp.yml`, `config/gcs_utils_config.yml`, etc.) resolve correctly.

**Confidence: HIGH** -- `os.chdir()` in a subprocess cannot affect parent processes (OS-level isolation).

### 3. How to handle venv activation in the subprocess command?

**Answer: Use the venv's Python binary directly. No activation needed.**

The current code already does this correctly:

```python
mcp_python = os.path.join(MIC_TRANSFORMER_CWD, ".venv", "bin", "python")
servers["mic-transformer"] = {
    "command": mcp_python,
    "args": [mcp_server_script],
}
```

Using `/home/bot/mic_transformer/.venv/bin/python` directly:
- Picks up all packages installed in that venv (mcp, fastmcp, sqlalchemy, google-cloud-storage, boto3, etc.)
- No need to `source activate` -- the Python binary itself embeds the venv path
- `sys.path` is set correctly by the Python interpreter automatically

**Confidence: HIGH** -- standard Python venv behavior, already implemented.

### 4. How to pass mic_transformer credentials to the MCP subprocess?

**Answer: Use the `env` field in the MCP server config dict.**

The Claude Agent SDK passes `env` through to the CLI's `--mcp-config` JSON. The CLI then sets these as environment variables for the MCP subprocess.

However, examining the mic-transformer MCP tools reveals they **do not use environment variables for most credentials**. Instead:

| Credential Type | How Tools Load It | Source |
|----------------|-------------------|--------|
| Database (IrisMedAppDB) | `yaml.safe_load('config/db_irismedapp.yml')` | YAML config file |
| GCS storage | `yaml.safe_load('config/gcs_utils_config.yml')` | YAML config file with embedded service account JSON |
| Google Drive | `yaml.safe_load('config/clinic_gdrive_config.yml')` | YAML config file |
| API URL | `os.getenv('MIC_TRANSFORMER_API_URL', 'http://136.111.85.127:8080')` | Env var with hardcoded default |
| Prefect API | Likely from config or env | Needs investigation on VM |

**Critical insight:** The tools rely on YAML config files under `config/` (loaded via relative paths after `os.chdir()`), NOT on environment variables. This means the `env` field in the MCP config is only needed for the one env var used (`MIC_TRANSFORMER_API_URL`) and potentially `PYTHONPATH` (though server.py handles this via `sys.path.insert`).

**The real prerequisite is that `config/*.yml` files exist in the mic_transformer clone on the VM with production credentials.**

**Confidence: HIGH** -- verified by reading actual tool source code.

### 5. What about the `PYTHONPATH` concern?

**Answer: Not needed. server.py handles it.**

`server.py` lines 23-25:
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'lib'))
```

This adds both `PROJECT_ROOT` and `PROJECT_ROOT/lib` to `sys.path` at import time, before any `from lib.models.IrisMedAppDB import ...` calls. No external PYTHONPATH env var needed.

**Confidence: HIGH** -- verified in server.py source.

## Data Flow: MCP Tool Invocation

```
User in Slack: "What's the VSP status for today?"
         │
         ▼
SuperBot handler → run_agent_with_timeout(prompt, session_id)
         │
         ▼
ClaudeAgentOptions(mcp_servers={"mic-transformer": {...}, "linear": {...}})
         │
         ▼
Claude CLI subprocess receives --mcp-config JSON
         │
         ▼
CLI spawns MCP servers on session start
         │  mic-transformer: /home/bot/mic_transformer/.venv/bin/python server.py
         │  linear: npx -y @anthropic/linear-mcp@latest
         │  sentry: npx -y @sentry/mcp-server@latest
         │
         ▼
Claude model sees all MCP tools in its tool list
         │
         ▼
Model decides to call mcp__mic-transformer__vsp_status(date="03.23.26")
         │
         ▼
CLI sends JSON-RPC request to mic-transformer subprocess via stdin
         │
         ▼
server.py routes to tools/status.py → vsp_status()
         │  - Opens config/db_irismedapp.yml (relative path, works because os.chdir)
         │  - Queries IrisMedAppDB PostgreSQL
         │  - Opens config/gcs_utils_config.yml
         │  - Checks GCS bucket for AIOUT files
         │
         ▼
Returns JSON result via stdout to CLI
         │
         ▼
CLI feeds result to Claude model → model generates response
         │
         ▼
SuperBot receives AssistantMessage text → posts to Slack thread
```

## Recommended `_build_mcp_servers()` Implementation

```python
def _build_mcp_servers() -> dict:
    """Build MCP server config dict from available credentials."""
    servers = {}

    # mic-transformer pipeline tools
    mcp_server_script = os.path.join(
        MIC_TRANSFORMER_CWD, ".claude", "mcp", "mic-transformer", "server.py"
    )
    mcp_python = os.path.join(MIC_TRANSFORMER_CWD, ".venv", "bin", "python")
    if os.path.isfile(mcp_server_script) and os.path.isfile(mcp_python):
        # server.py handles sys.path and os.chdir internally.
        # Most credentials come from config/*.yml files in the mic_transformer
        # repo, NOT from env vars. Only MIC_TRANSFORMER_API_URL uses os.getenv.
        mic_env = {}
        if config.MIC_TRANSFORMER_API_URL:
            mic_env["MIC_TRANSFORMER_API_URL"] = config.MIC_TRANSFORMER_API_URL

        server_config = {
            "command": mcp_python,
            "args": [mcp_server_script],
        }
        if mic_env:
            server_config["env"] = mic_env

        servers["mic-transformer"] = server_config
    else:
        log.warning(
            "mcp.mic_transformer_missing",
            script=mcp_server_script,
            python=mcp_python,
        )

    # ... linear, sentry unchanged ...
    return servers
```

## Integration Points Summary

| Integration Point | Type | Details |
|-------------------|------|---------|
| `_build_mcp_servers()` in agent.py | Modify | Add `env` dict with `MIC_TRANSFORMER_API_URL` |
| `config.py` | Modify | Add `MIC_TRANSFORMER_API_URL` env var |
| mic_transformer `.venv` | VM prerequisite | Must have `mcp`, `fastmcp` installed |
| mic_transformer `config/*.yml` | VM prerequisite | Must contain production credentials |
| mic_transformer clone | VM prerequisite | Already exists at `/home/bot/mic_transformer` |

## Anti-Patterns to Avoid

### Anti-Pattern 1: Trying to pass all .env vars through MCP `env` field
**What:** Parsing mic_transformer's `.env` file and passing every var through `env` dict.
**Why bad:** The tools don't use env vars for credentials -- they read YAML config files. Passing the .env would be cargo-culting and might expose unnecessary secrets to the Claude CLI's command-line (visible in `ps` output since `--mcp-config` is a CLI argument).
**Instead:** Ensure `config/*.yml` files exist on the VM. Only pass `MIC_TRANSFORMER_API_URL` if the default isn't correct.

### Anti-Pattern 2: Setting `PYTHONPATH` in the MCP env dict
**What:** Adding `"PYTHONPATH": "/home/bot/mic_transformer:/home/bot/mic_transformer/lib"` to the env.
**Why bad:** server.py already handles this via `sys.path.insert()`. Adding PYTHONPATH could cause import ordering issues if the values don't match exactly.
**Instead:** Trust server.py's existing path management.

### Anti-Pattern 3: Wrapping the command in a shell script for venv activation
**What:** `"command": "bash", "args": ["-c", "source .venv/bin/activate && python server.py"]`
**Why bad:** Unnecessary complexity. Using the venv's Python binary directly is the correct approach and is already implemented.
**Instead:** Keep current approach: `"command": "/home/bot/mic_transformer/.venv/bin/python"`

### Anti-Pattern 4: Adding a `cwd` field to the MCP config hoping the SDK supports it
**What:** Adding `"cwd": "/home/bot/mic_transformer"` to the server config dict.
**Why bad:** `McpStdioServerConfig` does not define a `cwd` field. While the dict might pass through to the CLI JSON, there's no guarantee the CLI handles it. And server.py already does `os.chdir(PROJECT_ROOT)` which achieves the same thing reliably.
**Instead:** Rely on server.py's internal `os.chdir()`.

## Scalability Considerations

| Concern | Current (v1.2) | Future |
|---------|----------------|--------|
| MCP server lifecycle | Started per Claude CLI session, killed when session ends | Acceptable -- sessions are short-lived (max 10min timeout) |
| Database connections | Created per tool call via `IrisMedAppDBConnection` | Could pool if tools are called frequently, but unlikely bottleneck |
| Multiple concurrent sessions | Each Claude CLI gets its own MCP subprocess | Fine -- no shared state between MCP instances |
| MCP server startup time | Python interpreter + imports + os.chdir | ~2-5 seconds, acceptable for first tool call |

## VM Prerequisites Checklist

Before the integration works, the VM must have:

1. **mic_transformer clone** at `/home/bot/mic_transformer` (already exists per PROJECT.md)
2. **mic_transformer .venv** with `mcp` and `fastmcp` packages:
   ```bash
   /home/bot/mic_transformer/.venv/bin/pip install mcp fastmcp
   ```
3. **config/*.yml files** with production credentials:
   - `config/db_irismedapp.yml` -- PostgreSQL connection for IrisMedAppDB
   - `config/gcs_utils_config.yml` -- GCS service account credentials
   - `config/clinic_gdrive_config.yml` -- Google Drive folder config
   - `config/clinic_gdrive_eyemed_config.yml` -- EyeMed-specific Drive config
   - `config/db_crystalpm_mirror.yml` -- CrystalPM mirror DB (for azure_mirror tools)
4. **Network access** from VM to:
   - PostgreSQL database (IrisMedAppDB)
   - Google Cloud Storage
   - Google Drive API
   - S3 (for remit PDFs)
   - Revolution EMR API
   - Prefect API
   - Azure SQL (for mirror)
5. **SSH key** for Prefect flow status checks (status tools SSH to production server)

## Suggested Build Order

1. **Verify VM prerequisites** -- check .venv has mcp/fastmcp, config/*.yml files exist
2. **Add `MIC_TRANSFORMER_API_URL` to config.py** -- single line addition
3. **Update `_build_mcp_servers()` in agent.py** -- add `env` dict (minimal change)
4. **Test locally** -- run SuperBot, send a simple MCP tool request (e.g., `vsp_status`)
5. **Validate all 13 tool modules** -- systematic test of each tool category

Steps 2-3 are trivial code changes (< 10 lines total). Step 1 (VM setup) and Step 5 (validation) are the real work.

## Sources

- Claude Agent SDK `types.py` -- `McpStdioServerConfig` definition (installed package, verified 2026-03-23)
- Claude Agent SDK `subprocess_cli.py` -- `--mcp-config` JSON serialization (installed package, verified 2026-03-23)
- mic-transformer `server.py` -- `os.chdir()`, `sys.path.insert()`, FastMCP setup (local source)
- mic-transformer `tools/*.py` -- credential loading patterns (local source)
- mic-transformer `lib/models/IrisMedAppDB.py` -- YAML config loading (local source)
- [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)
