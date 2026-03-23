# Domain Pitfalls: MCP Parity Integration

**Domain:** Adding a custom Python MCP server (fastmcp, stdio) to a Claude Agent SDK agent running as a systemd service on GCP VM
**Researched:** 2026-03-23
**Confidence:** HIGH (verified against Claude Agent SDK official docs, systemd behavior, and known GitHub issues)

---

## Critical Pitfalls

Mistakes that cause the MCP server to fail silently, leak credentials, or require architectural rework.

### Pitfall 1: MCP Server Missing Environment Variables Because `env` Field Replaces Instead of Extends

**What goes wrong:**
The mic-transformer MCP server needs dozens of environment variables (GCS credentials, S3 keys, Azure tokens, Prefect API URL, Revolution credentials, database connection strings). If you pass an `env` dict in the MCP server config, depending on how Claude Code internally spawns the subprocess, it may **replace** the inherited environment rather than extend it. The MCP server starts but every tool call fails with missing credential errors. The server itself appears "connected" in the init message -- the failure only surfaces when a tool is actually invoked.

**Why it happens:**
Python's `subprocess.Popen` behavior: if you pass `env={"KEY": "val"}`, it **replaces** the entire environment -- the subprocess gets ONLY that dict, losing PATH, HOME, and every other variable. The Claude Agent SDK's Python implementation currently spreads `os.environ` into the subprocess env (confirmed via [GitHub issue #573](https://github.com/anthropics/claude-agent-sdk-python/issues/573)), but this behavior is an implementation detail, not a documented guarantee. A future SDK update could change this.

**Consequences:**
- MCP server reports "connected" but every tool call returns cryptic errors about missing configs
- Hard to debug because the connection succeeds -- only tool execution fails
- If you add an `env` field to the mic-transformer config (e.g., to pass one extra variable), you might accidentally switch from "inherit everything" mode to "only these variables" mode

**Prevention:**
1. Do NOT pass an `env` field for the mic-transformer MCP server if all needed variables are already in the parent process environment (loaded via systemd `EnvironmentFile`). The current code correctly omits `env` for mic-transformer.
2. If you must add specific env vars, always merge with the parent environment explicitly:
   ```python
   "env": {**os.environ, "EXTRA_VAR": "value"}
   ```
3. Add a smoke test that invokes one MCP tool immediately after connection and verifies it returns real data, not an auth error.
4. Log the MCP server's stderr output -- fastmcp prints startup errors to stderr which the Claude Agent SDK captures via the `stderr` callback.

**Detection:**
- MCP server shows "connected" in init message but tool calls return errors
- Tool errors mention missing environment variables, config files, or credentials
- Works locally but fails under systemd

**Phase to address:** Phase 1 (wiring the MCP server into the agent) -- verify on first integration test.

---

### Pitfall 2: systemd EnvironmentFile Does Not Reach the MCP Subprocess

**What goes wrong:**
The superbot systemd service uses `EnvironmentFile=/home/bot/.env` to load variables. These variables are available to the Python bot process. When the Claude Agent SDK spawns the mic-transformer MCP subprocess, those variables should be inherited -- but they might not be, for several reasons:

1. The `.env` file uses shell syntax (e.g., `export VAR=val` or `VAR="val with spaces"`) that systemd's `EnvironmentFile` parser does not support. systemd's parser is NOT bash -- it handles simple `KEY=VALUE` lines only. Quoted values work but `export` prefixes, variable interpolation (`$OTHER_VAR`), and command substitution do not.
2. The MCP subprocess is spawned by Claude Code (a Node.js binary), which may apply its own environment filtering before spawning the stdio subprocess.
3. `PrivateTmp=true` in the systemd unit (line 24 of superbot.service) creates an isolated `/tmp` namespace. If the MCP server or any mic-transformer code writes to `/tmp` expecting shared access with other processes, it will silently use a private mount.

**Why it happens:**
Developers write `.env` files for local development using `dotenv` conventions (which support shell-like syntax). systemd `EnvironmentFile` has a much more restrictive parser. The file "works" locally because `python-dotenv` handles the shell syntax, but under systemd, variables with unsupported syntax are silently dropped.

**Consequences:**
- Some env vars present, others silently missing -- partial functionality
- MCP server works for some tools (those using present vars) but fails for others
- Extremely confusing to debug because it works locally

**Prevention:**
1. Ensure `/home/bot/.env` uses **only** systemd-compatible syntax: `KEY=VALUE` lines, no `export`, no `$VAR` interpolation, no backticks.
2. After deploying, SSH into the VM and verify: `sudo -u bot env | grep EXPECTED_VAR` to confirm the variable is actually set in the bot user's environment.
3. Add a startup health check in the bot that logs the presence (not values) of all required environment variables for mic-transformer tools.
4. Consider using a separate `EnvironmentFile` for mic-transformer-specific credentials to keep concerns isolated.

**Detection:**
- `systemctl show superbot --property=Environment` shows fewer variables than expected
- MCP tools that need specific credentials fail while others work
- Works when run manually (`sudo -u bot .venv/bin/python -m bot.app`) but fails under systemd

**Phase to address:** Phase 1 (VM environment setup) -- validate before wiring MCP.

---

### Pitfall 3: MCP Server `os.chdir()` Pollutes the Parent Process Working Directory

**What goes wrong:**
If the mic-transformer MCP server code (or any library it imports) calls `os.chdir()` at module import time or during initialization, and the MCP server runs **in-process** rather than as a true subprocess, the working directory change affects the entire bot process. Claude Agent SDK sessions that depend on `cwd` being the mic_transformer directory suddenly find themselves in a different directory.

**Why it happens:**
`os.chdir()` changes the process-wide working directory -- it affects all threads. In a stdio MCP server, this is a non-issue because the server runs as a separate process. But if someone refactors to use an in-process SDK MCP server (which the Claude Agent SDK supports as "SDK MCP servers"), or if a library uses `os.chdir()` during import and the import happens in the parent process, the CWD shifts globally.

**Consequences:**
- Claude Agent SDK sessions fail because `cwd` no longer points where expected
- Git operations fail (wrong repository)
- File reads/writes go to wrong locations
- Intermittent -- only happens after certain MCP tool calls

**Prevention:**
1. **Always use stdio transport** for the mic-transformer MCP server (the current architecture correctly does this). Never refactor to in-process.
2. Audit the MCP server's `server.py` and its imports for any `os.chdir()` calls. Grep the mic-transformer codebase: `grep -r "os.chdir" .`
3. If any mic-transformer tool needs to operate in a specific directory, use `subprocess.run(cwd=...)` or `contextlib.contextmanager` to scope the change, never bare `os.chdir()`.
4. The existing `MIC_TRANSFORMER_CWD = os.path.realpath(...)` pattern in `agent.py` is a good defensive measure -- keep it.

**Detection:**
- Agent errors mentioning "not a git repository" or "file not found" after MCP tool calls
- `os.getcwd()` returns unexpected path in logs
- Intermittent failures that correlate with specific MCP tool usage

**Phase to address:** Phase 1 (MCP server development/audit) -- verify before deployment.

---

### Pitfall 4: Credential Leaking Between MCP Servers via Inherited Environment

**What goes wrong:**
The Linear MCP server gets `LINEAR_API_KEY` via its `env` field. The Sentry MCP server gets `SENTRY_AUTH_TOKEN`. But because the Claude Agent SDK spreads `os.environ` into subprocess environments, **all** MCP servers receive **all** environment variables from the parent process. The mic-transformer MCP server (which has no `env` field) inherits LINEAR_API_KEY, SENTRY_AUTH_TOKEN, SLACK_BOT_TOKEN, SLACK_APP_TOKEN, and ANTHROPIC_API_KEY. A bug or prompt injection in any MCP server tool can access credentials meant for other servers.

**Why it happens:**
The `env` field in MCP server config is designed for adding variables the server needs, not for isolation. The underlying subprocess inherits the parent's full environment. This is standard Unix behavior but violates the principle of least privilege.

**Consequences:**
- A compromised or buggy MCP tool can read any credential in the environment
- Prompt injection in mic-transformer data (e.g., malicious content in a remittance PDF) could instruct Claude to use an MCP tool to exfiltrate env vars
- All credentials are one `os.environ` call away from any MCP server subprocess

**Prevention:**
1. **Accept the risk for this internal tool.** Full environment isolation for stdio MCP servers requires containerization (Docker) or separate systemd services per MCP server, which is overengineering for a small internal team.
2. Ensure the MCP server does NOT expose any tool that can read arbitrary environment variables or execute arbitrary code. Audit each tool function.
3. Never pass credentials as command-line arguments (visible in `ps aux`). Always use environment variables.
4. Keep the bot user's environment minimal -- only variables actually needed by any component. Do not put unrelated secrets in `/home/bot/.env`.

**Detection:**
- Run `cat /proc/<mcp-pid>/environ | tr '\0' '\n'` on the VM to see what the MCP subprocess actually has
- Audit MCP tool functions for `os.environ` access or shell command execution

**Phase to address:** Phase 1 (security review) -- document as accepted risk with mitigations.

---

### Pitfall 5: fastmcp Version Incompatibility with mcp Package Version

**What goes wrong:**
The mic-transformer MCP server imports from `fastmcp` (standalone package). The Claude Agent SDK's MCP client uses the `mcp` package internally. If the mic-transformer venv has `fastmcp==2.x` which depends on `mcp>=1.3`, but the superbot venv has a different `mcp` version, the MCP protocol negotiation can fail silently -- the server starts but protocol version mismatch causes tool calls to fail or return malformed responses.

**Why it happens:**
fastmcp is a standalone project that includes `mcp` as a dependency. The MCP protocol has evolved through versions (2024-11-05, 2025-03-26, etc.). If the server (fastmcp) and client (Claude Agent SDK / Claude Code) disagree on protocol version, the handshake may succeed but subsequent operations fail. FastMCP 1.0 was merged into the official `mcp` package, then FastMCP 2.0+ diverged as a standalone package with additional features.

**Consequences:**
- MCP server appears connected but tool calls return protocol errors
- Mysterious JSON-RPC errors in stderr
- Works with one version of Claude Code but breaks after an update

**Prevention:**
1. Pin `fastmcp` and `mcp` versions in the mic-transformer `requirements.txt`. Do not use `>=` -- use exact pins.
2. After any Claude Code update on the VM, test MCP connectivity before declaring the update complete.
3. Use the `system` init message to verify MCP server status is "connected" and tools are enumerated.
4. If fastmcp 2.x causes issues, consider using `from mcp.server.fastmcp import FastMCP` (the version bundled in the official `mcp` package) as a fallback.

**Detection:**
- stderr from MCP server contains JSON-RPC version mismatch errors
- MCP server shows "connected" but `mcp_servers` in init message shows 0 tools
- Tool calls return `MethodNotFound` or `InvalidRequest` errors

**Phase to address:** Phase 1 (dependency installation on VM) -- pin and verify versions.

---

### Pitfall 6: MCP Server Startup Timeout Kills Claude Session

**What goes wrong:**
The MCP SDK has a **default 60-second timeout** for server connections (documented in [Claude Agent SDK MCP docs](https://platform.claude.com/docs/en/agent-sdk/mcp)). The mic-transformer MCP server imports heavy dependencies (Flask, SQLAlchemy, boto3, google-cloud-storage, Prefect, etc.). On a cold start or an e2-small/medium VM with limited CPU, these imports can take 30-60+ seconds. If the server doesn't complete initialization within the timeout, it reports as "failed" and Claude has no MCP tools for the entire session.

**Why it happens:**
Python's import-time initialization is sequential. Large dependency trees (boto3 alone imports hundreds of modules) take measurable time on resource-constrained VMs. The 60-second timeout is fixed in the SDK and not configurable via the `mcp_servers` config.

**Consequences:**
- First request after VM restart or service restart fails because MCP server times out
- Intermittent failures under memory pressure when the VM is swapping
- Users see "MCP server failed to connect" in Claude's output

**Prevention:**
1. **Lazy-import heavy dependencies** in the MCP server. Only import boto3, google-cloud-storage, etc., inside the tool functions that use them, not at module top level.
2. Benchmark the MCP server startup time on the target VM: `time /path/to/venv/bin/python server.py` and ensure it completes well under 60 seconds.
3. Consider pre-warming: start the MCP server once at bot startup to populate Python's bytecode cache (`.pyc` files), then let the SDK restart it per session.
4. If the VM is too small, upgrade from e2-small to e2-medium. The $15/month difference is trivial compared to debugging timeout issues.

**Detection:**
- MCP server status is "failed" in the init message
- Works on the second request (bytecode cache warm) but fails on first
- `time python -c "import server"` shows >30 seconds

**Phase to address:** Phase 1 (VM sizing and MCP server optimization) -- test before deployment.

---

## Moderate Pitfalls

### Pitfall 7: MCP Server Crashes Silently, Claude Session Continues Without Tools

**What goes wrong:**
The mic-transformer MCP server crashes mid-session (unhandled exception, OOM kill, segfault in a C extension). Claude continues the session but all subsequent MCP tool calls fail. Claude may attempt to accomplish the task using its other tools (Read, Bash, etc.) which may produce incorrect or incomplete results, or it may report that the tool is unavailable -- but the user doesn't get a clear "MCP server died" notification.

**Prevention:**
1. Wrap all MCP tool functions in try/except with structured error responses rather than letting exceptions propagate.
2. Monitor the bot's stderr callback for MCP-related error messages and alert the user in Slack.
3. Add a health check tool to the MCP server (e.g., `mcp__mic-transformer__health_check`) that Claude can call to verify the server is alive.

---

### Pitfall 8: venv Python Path Breaks After mic-transformer Dependency Update

**What goes wrong:**
The MCP server is invoked as `/home/bot/mic_transformer/.venv/bin/python server.py`. If someone rebuilds the venv (deletes and recreates `.venv/`), the absolute path still exists but the venv may have a different Python version, missing packages, or broken symlinks. The MCP server fails to import `fastmcp` or other dependencies.

**Prevention:**
1. After any venv rebuild on the VM, restart the superbot service (`systemctl restart superbot`).
2. Add a deployment check that verifies `mcp_python` can actually import `fastmcp`: `subprocess.run([mcp_python, "-c", "import fastmcp"], check=True)` during bot startup.
3. Log a clear error in `_build_mcp_servers()` if the python binary exists but cannot import the MCP server module.

---

### Pitfall 9: MCP Server stdout Pollution Breaks JSON-RPC Protocol

**What goes wrong:**
The MCP stdio protocol uses stdout for JSON-RPC messages. If any code in the mic-transformer MCP server (or its dependencies) prints to stdout (via `print()`, logging to stdout, or a library that defaults to stdout), it corrupts the JSON-RPC stream. The Claude Agent SDK receives malformed JSON and the MCP connection dies.

**Prevention:**
1. **Never use `print()` in the MCP server.** Use `logging` module configured to write to stderr only.
2. Redirect any library that defaults to stdout (e.g., some Prefect client logging) to stderr.
3. In the MCP server entrypoint, add: `sys.stdout = sys.stderr` before starting fastmcp if you want to be extra safe (but test this -- fastmcp needs the real stdout for protocol messages).
4. Actually, the correct approach: configure Python logging to stderr only, and ensure no `print()` calls exist in any code path the MCP server executes.

---

### Pitfall 10: Multiple Claude Sessions Share One MCP Server Instance

**What goes wrong:**
If two Slack requests come in close together and the queue processes them sequentially (which it does), each `query()` call creates its own MCP server subprocess. But if there's any shared state on the filesystem (e.g., mic-transformer tools write to a shared temp file or lock file), the second session's MCP server may conflict with lingering resources from the first.

**Prevention:**
1. Ensure MCP server tools use unique temp directories per invocation (use `tempfile.mkdtemp()`).
2. The queue serialization in the current architecture mitigates this -- sessions don't run concurrently. But verify that MCP server subprocesses from the previous session are fully terminated before the next starts.
3. Check for stale `.lock` files or PID files that mic-transformer tools might create.

---

## Minor Pitfalls

### Pitfall 11: Tool Names Collide Between MCP Servers

**What goes wrong:**
If the mic-transformer MCP server exposes a tool named `status` and another MCP server also has a `status` tool, the namespacing `mcp__mic-transformer__status` vs `mcp__other__status` prevents collision at the protocol level. But Claude might get confused about which to call if the descriptions are similar.

**Prevention:**
Use descriptive, domain-specific tool names in the MCP server (e.g., `eyemed_status` not `status`). The current mic-transformer MCP server already follows this convention.

---

### Pitfall 12: `PrivateTmp=true` Breaks Temp File Sharing

**What goes wrong:**
The superbot.service has `PrivateTmp=true`. The MCP subprocess (spawned by the bot process) inherits this private `/tmp` namespace. If any mic-transformer tool writes files to `/tmp` expecting them to be readable by other processes (e.g., writing a CSV for later retrieval), those files are invisible outside the service's namespace.

**Prevention:**
Use a dedicated directory under `/home/bot/` for shared files instead of `/tmp`. The `PrivateTmp` isolation is good security practice -- do not remove it. Instead, configure mic-transformer tools to use a specific output directory.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Wiring MCP server into agent.py | Pitfall 1 (env not reaching subprocess) | Test with one tool call immediately after connection |
| Installing dependencies on VM | Pitfall 5 (version mismatch) | Pin fastmcp and mcp versions; test protocol handshake |
| VM environment setup | Pitfall 2 (systemd EnvironmentFile syntax) | Validate all env vars are present via startup health check |
| First end-to-end test | Pitfall 6 (startup timeout) | Benchmark import time; lazy-load heavy deps |
| Security review | Pitfall 4 (credential leaking) | Accept risk, audit tools for env access |
| Production deployment | Pitfall 9 (stdout pollution) | Audit for print() statements; redirect logging to stderr |
| MCP server development | Pitfall 3 (os.chdir) | Grep codebase; use subprocess cwd param |

---

## "Looks Done But Isn't" Checklist for MCP Parity

- [ ] **Every env var reaches MCP subprocess:** Run a tool that uses GCS credentials, S3 credentials, and Prefect API -- all three work, not just the first one tested.
- [ ] **Works under systemd, not just manual run:** Do NOT test only with `sudo -u bot python -m bot.app`. Test via `systemctl start superbot` specifically.
- [ ] **Startup time under 60 seconds:** Time the MCP server cold start on the actual VM. Not on your local machine.
- [ ] **No print() in MCP server code path:** `grep -r "print(" server.py tools/` returns zero hits in production code paths.
- [ ] **Tool calls return real data:** At least one tool from each of the 13 modules returns actual production data, not just "connected successfully."
- [ ] **MCP server crash doesn't crash the bot:** Kill the MCP server process mid-session; verify the bot reports the error to Slack and recovers for the next request.
- [ ] **Second request works after first:** The first Slack request uses MCP tools successfully. The second request (new session) also works -- no stale state.
- [ ] **fastmcp version pinned:** `pip freeze | grep fastmcp` on the VM shows an exact version, not a range.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Env vars missing in MCP subprocess | LOW | Add vars to EnvironmentFile, restart service, verify |
| MCP server timeout on startup | LOW | Lazy-load imports, restart service, or upgrade VM |
| Protocol version mismatch | MEDIUM | Pin correct fastmcp version, rebuild venv, restart |
| stdout pollution killing JSON-RPC | MEDIUM | Find and fix print() call, restart service |
| Credential leak via env inheritance | HIGH | Rotate leaked credentials, audit MCP tool functions, restrict env |
| os.chdir corrupting CWD | MEDIUM | Restart service, fix offending code, add defensive checks |

---

## Sources

- [Claude Agent SDK MCP Documentation](https://platform.claude.com/docs/en/agent-sdk/mcp) -- official, HIGH confidence (60-second timeout, env field usage, init message for status checking)
- [Claude Agent SDK Python GitHub Issue #573: Subprocess inherits CLAUDECODE=1](https://github.com/anthropics/claude-agent-sdk-python/issues/573) -- official GitHub, HIGH confidence (confirms os.environ spreading to subprocess)
- [FastMCP GitHub Issue #399: STDIO initialize succeeds, subsequent requests crash](https://github.com/jlowin/fastmcp/issues/399) -- official GitHub, HIGH confidence (known RuntimeError after init)
- [FastMCP GitHub Issue #1311: Client doesn't properly close stdio MCP](https://github.com/jlowin/fastmcp/issues/1311) -- official GitHub, HIGH confidence (subprocess cleanup issues)
- [MCP Python SDK Issue #671: Tool execution hangs in stdio mode](https://github.com/modelcontextprotocol/python-sdk/issues/671) -- official GitHub, HIGH confidence (external script hanging)
- [Setting Environment Variables for systemd Services (Baeldung)](https://www.baeldung.com/linux/systemd-services-environment-variables) -- MEDIUM confidence (well-known reference, verified against systemd docs)
- [Python venv and systemd interaction](https://www.pythontutorials.net/blog/how-to-enable-a-virtualenv-in-a-systemd-service-unit/) -- MEDIUM confidence (community, widely corroborated)
- [FastMCP PyPI page](https://pypi.org/project/fastmcp/) -- official, HIGH confidence (version history, dependency chain)
- [FastMCP 2.0 vs MCP Python SDK Server (GitHub Issue #1068)](https://github.com/modelcontextprotocol/python-sdk/issues/1068) -- official GitHub, MEDIUM confidence (version compatibility discussion)

---
*Pitfalls research for: v1.2 MCP Parity -- adding mic-transformer MCP server to SuperBot*
*Researched: 2026-03-23*
