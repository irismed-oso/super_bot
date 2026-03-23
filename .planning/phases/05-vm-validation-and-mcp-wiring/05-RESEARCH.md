# Phase 5: VM Validation and MCP Wiring - Research

**Researched:** 2026-03-23
**Domain:** MCP stdio subprocess wiring under systemd, VM credential validation, cold-start benchmarking
**Confidence:** HIGH

## Summary

Phase 5 is a deployment and validation phase, not a feature development phase. The code for wiring the mic-transformer MCP server into SuperBot already exists in `bot/agent.py` (commit `d66d523`). The `_build_mcp_servers()` function already detects the mic-transformer server script and Python binary, and passes them to `ClaudeAgentOptions.mcp_servers` as a stdio config. The only code change is adding an optional feature flag override (env var to disable the server for troubleshooting).

The real work is VM-side: (1) install `mcp[cli]~=1.26.0` in mic_transformer's venv, (2) copy credential YAML files to the VM, (3) audit the systemd EnvironmentFile for syntax incompatibilities, (4) benchmark MCP server cold-start time against the 60-second SDK timeout, and (5) deploy, restart, and prove end-to-end connectivity with a `check_pipeline_status` tool call through Slack.

The primary risk is silent env var loss under systemd's restrictive EnvironmentFile parser and MCP server startup timeout due to heavy Python imports (boto3, google-cloud-storage, SQLAlchemy). Both are detectable and fixable before feature testing begins.

**Primary recommendation:** Deploy credentials and dependencies to VM first, benchmark cold-start, then deploy code and test via Slack -- validate infrastructure before wiring.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Copy config/*.yml files from local dev machine to VM's /home/bot/mic_transformer/config/ via SCP
- SSH access to production server (136.111.85.127) for Prefect tools: unknown, verify during implementation
- Cloud SQL network access (34.136.128.245): unknown, verify firewall rules during implementation
- MCP server enabled by default if mic_transformer path exists on disk -- no explicit MIC_TRANSFORMER_MCP_ENABLED env var needed to turn on
- Still provide a way to disable (env var override) for troubleshooting
- Use check_pipeline_status as the proof tool -- broader scope, checks multiple systems
- Test directly via Slack @mention (skip local test script)
- Deploy code, deploy credentials, restart service, then immediately test via Slack
- If MCP cold-start exceeds 60-second timeout, use pre-warming approach
- Benchmark cold-start time on VM first; only implement pre-warming if needed

### Claude's Discretion
- Env var propagation approach (inherit from SuperBot vs separate .env for mic_transformer)
- Pre-warming implementation details (ExecStartPre vs startup script vs other)
- MCP server command/args format in _build_mcp_servers()
- How to handle missing credentials gracefully (warn vs fail)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MCPW-01 | mic-transformer MCP server added to _build_mcp_servers() in agent.py as stdio subprocess | Already implemented in agent.py (commit d66d523). Code uses mic_transformer's venv python + server.py path. Only enhancement: add feature flag disable override. |
| MCPW-02 | MIC_TRANSFORMER_MCP_ENABLED config flag controls whether mic-transformer MCP server is wired | Per CONTEXT.md: enabled by default when path exists on disk. Add env var override to disable only. Add to config.py, check in _build_mcp_servers(). |
| MCPW-03 | mcp[cli]~=1.26.0 installed in mic_transformer .venv on VM | VM task: run `/home/bot/mic_transformer/.venv/bin/pip install 'mcp[cli]~=1.26.0'`. Verify with import test. |
| VMEV-01 | mic_transformer config/*.yml credential files present and valid on VM | SCP from local dev machine. At minimum: config.yml, secrets.yml, gcs_utils_config.yml, db_irismedapp.yml. Verify by running check_pipeline_status manually. |
| VMEV-02 | systemd EnvironmentFile syntax validated (no export, no interpolation) | Audit /home/bot/.env for lines starting with `export`, containing `$`, or using backticks. systemd silently drops these. |
| VMEV-03 | MCP server cold-start completes within 60-second SDK timeout on VM hardware | Benchmark: `time /home/bot/mic_transformer/.venv/bin/python /home/bot/mic_transformer/.claude/mcp/mic-transformer/server.py` (will hang on stdin, measure startup time). If >30s, consider lazy imports or pre-warming. |
</phase_requirements>

## Standard Stack

### Core (Already Installed -- No Changes to SuperBot)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| claude-agent-sdk | 0.1.49 | Agent engine with mcp_servers support | Already installed in super_bot venv |
| slack-bolt | 1.27.0 | Slack event handling | Already installed |
| structlog | any | Structured logging | Already installed |

### New Dependency (mic_transformer venv only)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mcp[cli] | ~=1.26.0 | MCP server runtime (bundles FastMCP at mcp.server.fastmcp) | Official Anthropic MCP SDK; server.py already imports from this path |

### Do NOT Install
| Package | Why Not |
|---------|---------|
| fastmcp (standalone PyPI) | Different project by jlowin/Prefect. server.py imports from `mcp.server.fastmcp`, NOT standalone `fastmcp`. Would be unused and risks import shadowing. |

**Installation (on VM only):**
```bash
/home/bot/mic_transformer/.venv/bin/pip install 'mcp[cli]~=1.26.0'
# Verify:
/home/bot/mic_transformer/.venv/bin/python -c "from mcp.server.fastmcp import FastMCP; print('OK')"
```

## Architecture Patterns

### Existing MCP Wiring (Already Implemented)

The `_build_mcp_servers()` function in `bot/agent.py` (lines 43-78) already contains the mic-transformer wiring:

```python
# Already exists in agent.py
mcp_server_script = os.path.join(
    MIC_TRANSFORMER_CWD, ".claude", "mcp", "mic-transformer", "server.py"
)
mcp_python = os.path.join(MIC_TRANSFORMER_CWD, ".venv", "bin", "python")
if os.path.isfile(mcp_server_script) and os.path.isfile(mcp_python):
    servers["mic-transformer"] = {
        "command": mcp_python,
        "args": [mcp_server_script],
    }
```

**Key design:** No `env` field is passed. The MCP subprocess inherits the parent process environment automatically. This is correct because mic-transformer tools load credentials from `config/*.yml` files via `os.chdir(PROJECT_ROOT)` at server startup, not from environment variables. The only env vars needed are standard ones (PATH, HOME) which are inherited.

### Pattern: Feature Flag Override

Per CONTEXT.md, the server is enabled by default when the path exists. Add a disable override:

```python
# In config.py -- add one line:
MIC_TRANSFORMER_MCP_DISABLED: bool = os.environ.get("MIC_TRANSFORMER_MCP_DISABLED", "").lower() in ("1", "true", "yes")

# In agent.py _build_mcp_servers() -- wrap existing check:
if (not config.MIC_TRANSFORMER_MCP_DISABLED
        and os.path.isfile(mcp_server_script) and os.path.isfile(mcp_python)):
    servers["mic-transformer"] = {
        "command": mcp_python,
        "args": [mcp_server_script],
    }
else:
    if config.MIC_TRANSFORMER_MCP_DISABLED:
        log.info("mcp.mic_transformer_disabled_by_env")
    else:
        log.warning("mcp.mic_transformer_missing", ...)
```

**Rationale for "disabled" flag (not "enabled"):** The CONTEXT.md decision is "enabled by default if path exists." A `_DISABLED` flag inverts cleanly: unset = enabled (default), set to true = disabled for troubleshooting. This avoids the "forgot to set the enable flag" failure mode.

### Pattern: McpStdioServerConfig Shape

From the SDK source (claude_agent_sdk/types.py lines 498-504):

```python
class McpStdioServerConfig(TypedDict):
    type: NotRequired[Literal["stdio"]]  # Optional
    command: str
    args: NotRequired[list[str]]
    env: NotRequired[dict[str, str]]
    # NO cwd field exists
```

The server handles its own cwd via `os.chdir(PROJECT_ROOT)` at startup. This is correct and does not pollute the parent process because stdio MCP servers run as separate subprocesses.

### Deployment Sequence

```
1. SSH to VM
2. Install mcp[cli] in mic_transformer venv
3. SCP config/*.yml files to /home/bot/mic_transformer/config/
4. Audit /home/bot/.env for systemd syntax issues
5. Pull latest super_bot code (includes feature flag)
6. Restart superbot service
7. Benchmark cold-start from journalctl logs
8. Test via Slack: @SuperBot check pipeline status for Beverly today
```

### Anti-Patterns to Avoid
- **Do NOT pass `env` dict to mic-transformer server config** unless absolutely required. Passing ANY `env` field risks replacing the entire inherited environment (Python subprocess.Popen behavior). The SDK currently merges, but this is undocumented behavior.
- **Do NOT install mcp[cli] in super_bot's venv.** It goes in mic_transformer's venv only. The MCP server is spawned using mic_transformer's Python binary.
- **Do NOT add a local test script.** Per CONTEXT.md, testing is done directly via Slack @mention after deployment.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP server process management | Custom subprocess.Popen wrapper | Claude Agent SDK's built-in stdio MCP spawning | SDK handles lifecycle, stdin/stdout framing, JSON-RPC protocol |
| Feature flag | Custom config file or database | Simple env var check in config.py | Only needs on/off; env var is simplest, works with systemd EnvironmentFile |
| Cold-start optimization | Custom process pool or warm cache | Lazy imports in server.py tool modules (if needed) | The SDK spawns fresh subprocess per session; cannot pre-warm across sessions |
| Credential validation | Custom health-check endpoint | Manual `check_pipeline_status` tool call through Slack | The tool itself validates GCS, S3, GDrive, DB access in one call |

## Common Pitfalls

### Pitfall 1: systemd EnvironmentFile Silently Drops Variables
**What goes wrong:** `/home/bot/.env` uses `export KEY=val` or `$VAR` interpolation syntax. systemd's parser silently ignores these lines. Variables present locally vanish on VM.
**Why it happens:** Developers write `.env` files for python-dotenv (which handles shell syntax). systemd EnvironmentFile only supports bare `KEY=VALUE`.
**How to avoid:** Audit `/home/bot/.env` with: `grep -E '^export |\\$|`' /home/bot/.env`. Fix any matches to bare `KEY=VALUE` format.
**Warning signs:** MCP tools work for some operations but fail for others; "works locally" but fails under systemd.

### Pitfall 2: MCP Server Startup Timeout (60-Second SDK Limit)
**What goes wrong:** mic-transformer imports boto3, google-cloud-storage, SQLAlchemy, requests, and other heavy packages. On a cold VM (no .pyc cache), first import can take 15-30+ seconds. If total startup exceeds 60 seconds, the SDK kills the connection and the session fails.
**Why it happens:** Python's import system compiles .py to .pyc on first run. Large packages (boto3 has ~1500 modules) take significant time on first cold import.
**How to avoid:** Benchmark on the actual VM. If startup approaches 30s, move heavy imports inside tool functions (lazy import pattern). Pre-compile .pyc files by running the server once manually.
**Warning signs:** First-ever tool call fails with timeout; subsequent calls succeed (because .pyc files now exist).

### Pitfall 3: Wrong mic_transformer Python Binary
**What goes wrong:** The MCP server is spawned with `/home/bot/mic_transformer/.venv/bin/python` but this venv doesn't have `mcp[cli]` installed, or the venv is broken/stale.
**Why it happens:** `mcp[cli]` must be installed in mic_transformer's venv, not super_bot's. If someone rebuilds the venv without including mcp, the server fails.
**How to avoid:** Verify after install: `/home/bot/mic_transformer/.venv/bin/python -c "from mcp.server.fastmcp import FastMCP; print('OK')"`. Add this check to the deploy script.
**Warning signs:** MCP server shows "failed" status in logs; stderr mentions ImportError for mcp.server.fastmcp.

### Pitfall 4: Config YAML Files Missing on VM
**What goes wrong:** The mic-transformer server calls `os.chdir(PROJECT_ROOT)` then loads `config/*.yml` files using relative paths. If these files don't exist on the VM (they're gitignored), every tool that needs credentials fails.
**Why it happens:** Config files contain secrets and are gitignored. The VM's git clone doesn't include them. They must be manually copied.
**How to avoid:** SCP the files from local dev machine. Verify key files exist: `config.yml`, `secrets.yml`, `gcs_utils_config.yml`, `db_irismedapp.yml`, `db_crystalpm_mirror.yml`, `clinic_gdrive_config.yml`, `clinic_gdrive_eyemed_config.yml`.
**Warning signs:** MCP server connects but tool calls return "FileNotFoundError" or "No such file or directory" errors mentioning config/*.yml.

### Pitfall 5: Credential Files Have Dev Values Instead of Production
**What goes wrong:** Config files are copied but contain localhost DB connections or dev GCS buckets. Tools return empty results or connect to wrong databases.
**Why it happens:** Dev machine config points to local/dev resources. VM needs production credentials.
**How to avoid:** Use the `.prod` suffix files where available (e.g., `db_irismedapp.yml.prod` -> `db_irismedapp.yml`). For the proof-of-concept test (`check_pipeline_status`), this tool hits the production Flask API at `http://136.111.85.127:8080` (via `API_BASE_URL` in common.py), so it needs network access to that IP from the VM.

### Pitfall 6: Network Access from VM to Production Server
**What goes wrong:** `check_pipeline_status` and many tools call `API_BASE_URL` (136.111.85.127:8080) or SSH to `PREFECT_HOST` (136.111.85.127). If the GCP VM firewall blocks outbound access to these IPs, tools fail with connection timeouts.
**Why it happens:** GCP VPC firewall rules may restrict egress. The production server is on a different network.
**How to avoid:** Test connectivity before deploying: `curl -s http://136.111.85.127:8080/version` from the VM. If blocked, add firewall rule.
**Warning signs:** Tool calls hang for 30+ seconds then return connection timeout errors.

## Code Examples

### Feature Flag Addition (config.py)
```python
# Source: CONTEXT.md locked decision + Claude's discretion
# Add after existing env var mappings:
MIC_TRANSFORMER_MCP_DISABLED: bool = os.environ.get(
    "MIC_TRANSFORMER_MCP_DISABLED", ""
).lower() in ("1", "true", "yes")
```

### Updated _build_mcp_servers() (agent.py)
```python
# Source: Existing code + feature flag wrapper
def _build_mcp_servers() -> dict:
    servers = {}

    # mic-transformer pipeline tools
    mcp_server_script = os.path.join(
        MIC_TRANSFORMER_CWD, ".claude", "mcp", "mic-transformer", "server.py"
    )
    mcp_python = os.path.join(MIC_TRANSFORMER_CWD, ".venv", "bin", "python")

    if config.MIC_TRANSFORMER_MCP_DISABLED:
        log.info("mcp.mic_transformer_disabled_by_env")
    elif os.path.isfile(mcp_server_script) and os.path.isfile(mcp_python):
        servers["mic-transformer"] = {
            "command": mcp_python,
            "args": [mcp_server_script],
        }
    else:
        log.warning(
            "mcp.mic_transformer_missing",
            script=mcp_server_script,
            python=mcp_python,
        )

    # ... rest of linear/sentry servers unchanged
```

### Deploy Script (scripts/deploy_v1.2_phase5.sh)
```bash
#!/usr/bin/env bash
set -euo pipefail

VM="superbot-vm"
ZONE="us-west1-a"
SSH="gcloud compute ssh bot@${VM} --zone=${ZONE} --"

echo "=== Step 1: Install mcp[cli] in mic_transformer venv ==="
$SSH "
  /home/bot/mic_transformer/.venv/bin/pip install 'mcp[cli]~=1.26.0'
  /home/bot/mic_transformer/.venv/bin/python -c 'from mcp.server.fastmcp import FastMCP; print(\"OK\")'
"

echo "=== Step 2: Copy config files (run SCP separately) ==="
echo "Run from local machine:"
echo "  scp -r /path/to/mic_transformer/config/*.yml bot@VM_IP:/home/bot/mic_transformer/config/"

echo "=== Step 3: Audit .env for systemd compatibility ==="
$SSH "grep -nE '^export |\\$[A-Z]|^\`' /home/bot/.env && echo 'FIX ABOVE LINES' || echo '.env syntax OK'"

echo "=== Step 4: Benchmark MCP cold-start ==="
$SSH "
  timeout 60 bash -c '
    START=\$(date +%s%N)
    echo | /home/bot/mic_transformer/.venv/bin/python /home/bot/mic_transformer/.claude/mcp/mic-transformer/server.py &
    PID=\$!
    sleep 5
    kill \$PID 2>/dev/null
    END=\$(date +%s%N)
    echo \"Startup time: \$(( (END - START) / 1000000 )) ms\"
  '
"

echo "=== Step 5: Test network connectivity to production ==="
$SSH "curl -s -o /dev/null -w '%{http_code}' http://136.111.85.127:8080/version || echo 'BLOCKED - need firewall rule'"

echo "=== Step 6: Pull latest super_bot and restart ==="
$SSH "
  sudo -u bot bash -c 'cd /home/bot/super_bot && git pull origin main'
  sudo systemctl restart superbot
  sleep 3
  sudo systemctl status superbot --no-pager
"

echo "=== Step 7: Check MCP server registration in logs ==="
$SSH "sudo journalctl -u superbot -n 50 --no-pager | grep -E 'mcp|mic.transformer' || echo 'Check logs manually'"

echo ""
echo "=== Test via Slack ==="
echo "@SuperBot check pipeline status for Beverly today"
```

### Cold-Start Benchmark Command
```bash
# Run on VM -- measures time for server.py to initialize (before it blocks on stdin)
time /home/bot/mic_transformer/.venv/bin/python -c "
import sys, os
sys.path.insert(0, '/home/bot/mic_transformer')
sys.path.insert(0, '/home/bot/mic_transformer/lib')
os.chdir('/home/bot/mic_transformer')
from mcp.server.fastmcp import FastMCP
# Import all tool modules (this is what takes time)
from tools import analytics, azure_mirror, benefits, crawler, deploy, extraction, gdrive, ingestion, ivt_ingestion, posting, reduction, status, storage
print('All modules imported successfully')
"
```

### Pre-Warming via ExecStartPre (if needed)
```ini
# Add to systemd/superbot.service ONLY if cold-start exceeds 30s
[Service]
ExecStartPre=/home/bot/mic_transformer/.venv/bin/python -c "import sys; sys.path.insert(0, '/home/bot/mic_transformer'); sys.path.insert(0, '/home/bot/mic_transformer/lib'); from tools import status, storage"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate .env for MCP server | Inherit parent env + config/*.yml files | Already implemented | No env field needed in MCP config; simpler |
| MIC_TRANSFORMER_MCP_ENABLED flag | Enabled-by-default with _DISABLED override | CONTEXT.md decision | Avoids "forgot to set" failure mode |
| Local test script verification | Direct Slack @mention testing | CONTEXT.md decision | Tests the full end-to-end path |

## Open Questions

1. **Network access from VM to production server (136.111.85.127)**
   - What we know: MCP tools use `API_BASE_URL = http://136.111.85.127:8080` and SSH to `PREFECT_HOST = 136.111.85.127`
   - What's unclear: Whether GCP VM firewall allows outbound to this IP
   - Recommendation: Test with `curl` before deploying code; add firewall rule if blocked

2. **Which config/*.yml files are strictly required for check_pipeline_status?**
   - What we know: check_pipeline_status calls the Flask API at API_BASE_URL, plus checks GCS and GDrive. It imports from `tools/common.py` which uses hardcoded constants, and from `tools/storage.py` which uses boto3/google-cloud-storage.
   - What's unclear: Exact config files loaded by the GCS/S3 client initialization
   - Recommendation: Copy all config/*.yml files to be safe; the tool will error clearly if a specific file is missing

3. **MCP server cold-start time on VM**
   - What we know: Heavy imports (boto3 ~1500 modules, google-cloud-storage, SQLAlchemy). SDK timeout is 60 seconds.
   - What's unclear: Actual time on the GCP VM (e2-medium, 2 vCPU, 4GB RAM typical)
   - Recommendation: Benchmark before deploying. If >30s, lazy-import heavy modules. Pre-compile .pyc by running import once manually.

## Sources

### Primary (HIGH confidence)
- `bot/agent.py` lines 43-78 -- existing _build_mcp_servers() implementation with mic-transformer already wired
- `claude_agent_sdk/types.py` lines 498-504 -- McpStdioServerConfig TypedDict (command, args, env; no cwd)
- `mic_transformer/.claude/mcp/mic-transformer/server.py` -- server startup: os.chdir(PROJECT_ROOT), sys.path setup, FastMCP import
- `mic_transformer/.claude/mcp/mic-transformer/tools/common.py` -- API_BASE_URL, PREFECT_HOST constants
- `systemd/superbot.service` -- EnvironmentFile=/home/bot/.env, User=bot
- `config.py` -- existing env var mappings
- `.planning/research/PITFALLS.md` -- 12-pitfall inventory from v1.2 roadmap research

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` -- integration data flow diagram
- `.planning/research/SUMMARY.md` -- stack recommendations and deployment sequence

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - verified from installed packages and existing code
- Architecture: HIGH - code already exists, minimal changes needed
- Pitfalls: HIGH - verified against systemd docs, SDK source, and prior project research
- VM validation: MEDIUM - network access and cold-start time are unknowns until tested on VM

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (stable -- no fast-moving dependencies)
