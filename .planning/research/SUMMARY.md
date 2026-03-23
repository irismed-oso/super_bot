# Project Research Summary

**Project:** SuperBot v1.2 MCP Parity
**Domain:** Slack-integrated autonomous coding and operations agent with mic-transformer MCP tool integration
**Researched:** 2026-03-23 (v1.2 update; baseline research 2026-03-18)
**Confidence:** HIGH

## Executive Summary

SuperBot v1.2 is a tightly scoped integration milestone: wire the existing mic-transformer MCP server (35+ operational tools across 13 modules) into SuperBot's Claude Agent SDK sessions so Nicole and Han can invoke production pipeline operations directly from Slack. The architecture is already correct — `_build_mcp_servers()` in `bot/agent.py` already wires the mic-transformer server as a stdio subprocess using mic_transformer's own Python interpreter. The code changes required are minimal (under 10 lines across two files). The real work is VM prerequisite validation and systematic credential verification across four distinct credential pathways (GCS, S3, Google Drive, PostgreSQL).

The recommended approach is to deploy in four phases ordered by credential complexity and operational blast radius: start with the 20+ read-only status and audit tools (no risk to production data), then API-triggered mutating tools (validated by the production Flask API before reaching Celery workers), then SSH and Prefect tools (remote execution but no local subprocess exposure), and finally subprocess-based mutating tools (autopost, posting prep) which interact with Revolution EMR and require the most careful dry-run testing. The key distinction from all commercial agents (Claude Code in Slack, Kilo, GitHub Copilot) is that no commercial product ships with 35+ domain-specific operational tools. MCP integration transforms SuperBot from a coding agent into an operational platform where Nicole can ask "what's the VSP status for today?" and get a real answer pulling from GCS, S3, Google Drive, and PostgreSQL simultaneously.

The most significant risks are environment variable propagation under systemd and MCP server startup timeout due to heavy Python dependency imports. Both are addressable before any feature testing: validate that `/home/bot/.env` uses strict `KEY=VALUE` systemd syntax (no `export` prefix, no shell variable interpolation), and benchmark the MCP server cold-start time on the actual GCP VM — it must complete under the SDK's fixed 60-second connection timeout. The credential model is correct: mic-transformer tools load credentials from `config/*.yml` files via relative paths after `os.chdir(PROJECT_ROOT)`, not from environment variables, so the primary deployment prerequisite is verifying those YAML config files exist on the VM with production values.

## Key Findings

### Recommended Stack

SuperBot's existing stack requires no changes for v1.2. The only new dependency is `mcp[cli]~=1.26.0` installed in mic_transformer's venv (NOT super_bot's venv). This is the official Anthropic MCP Python SDK, which bundles FastMCP 1.0 at `mcp.server.fastmcp`. The mic-transformer server already imports from this path (`from mcp.server.fastmcp import FastMCP`). Do NOT install the standalone `fastmcp` PyPI package — it is a separate project maintained by Prefect/jlowin that would be unused and could cause import shadowing.

See [STACK.md](STACK.md) for full version compatibility matrix and alternatives considered.

**Core technologies:**
- `claude-agent-sdk==0.1.49`: Agent engine with `mcp_servers` support — already installed, no change needed
- `mcp[cli]~=1.26.0` (in mic_transformer venv only): MCP server runtime — the only new package; one `pip install` command
- `McpStdioServerConfig` type (SDK): defines `command`, `args`, and optional `env` fields — no `cwd` field exists or is needed
- `FastMCP` (bundled inside `mcp` package): already used by server.py; no server code changes required
- Systemd `EnvironmentFile=/home/bot/.env`: credential delivery to bot process — must use strict `KEY=VALUE` syntax, no shell extensions

### Expected Features

SuperBot v1.2 must expose all 35+ mic-transformer MCP tools through a single stdio subprocess wired into each Claude Agent SDK session. Tools divide into a clear risk hierarchy: read-only queries with no blast radius, API-mediated writes validated by the production Flask API, Prefect-triggered remote jobs, and local subprocess execution.

See [FEATURES.md](FEATURES.md) for the complete 35+ tool inventory with per-tool credentials and complexity ratings.

**Must have (table stakes for MCP parity):**
- All 11 Module 1 status/audit tools — Nicole's primary workflow starts with "what's the status?"; requires GCS, S3, GDrive, DB, and SSH credentials
- All Module 5 read-only storage tools (5 tools) — "did the PDF arrive? is the AIOUT there?"
- Module 2 extraction triggers (`vsp_extract`, `eyemed_extract`, `requeue_missing_pages`) — daily operational workflow
- Module 3 reduction triggers (`reduce_aiout`, `reduce_all_vsp`) — daily workflow immediately after extraction
- Module 10 deploy version check — validates end-to-end MCP connectivity with zero risk
- `check_prefect_flow_status`, `get_prefect_logs` — diagnosing why pipeline stages are not processing

**Should have (differentiators beyond coding agents):**
- Module 4 posting prep (3 tools) — prepare GDrive and GCS files for manual posting team
- Module 9 benefits fetch (3 tools) — trigger and poll long-running Prefect jobs from Slack; up to 10-minute polling
- Module 11 azure mirror audit and trigger — 24-location CrystalPM sync monitoring from Slack
- Module 12 IVT ingestion audit — cross-system health check (Prefect + prod-ivt DB)
- Module 13 provider revenue analytics — business intelligence query from Slack
- Module 4 autopost tools (`vsp_autopost`, `eyemed_autopost`) — `dry_run=True` default; highest operational value but highest risk; test dry_run exhaustively before live use

**Defer to v2+:**
- `remit_crawler` (Module 6) — requires Chrome/Chromium headless browser on GCP VM and insurance portal credentials; unclear if viable; interim workaround: SSH to production server for manual crawler invocation

**Anti-features to reject:**
- Approval gates on mutating MCP tools — PROJECT.md explicitly scopes this out; full autonomy by design; team visibility in channel is the audit trail
- Custom wrappers around MCP tools — tools have clean interfaces; wiring the server as stdio subprocess makes all 35+ tools available automatically
- Tool-level access control — only 2-3 trusted users; existing Slack allowlist from v1.0 is sufficient

### Architecture Approach

The integration architecture is a pure subprocess model requiring minimal code changes. SuperBot's `_build_mcp_servers()` passes mic_transformer's venv Python binary plus the `server.py` path to `ClaudeAgentOptions.mcp_servers`. The Claude CLI spawns the MCP server as a stdio subprocess per `query()` call; the subprocess lives only for that session's duration and is killed by the CLI when the session ends. No persistent MCP server process management is needed. The MCP server calls `os.chdir(PROJECT_ROOT)` internally at startup, making all relative-path `config/*.yml` credential loads work regardless of spawn directory. Each session gets a fresh subprocess instance with no shared state between sessions.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full data flow diagram, anti-patterns, and recommended `_build_mcp_servers()` implementation.

**Major components:**
1. `bot/agent.py` `_build_mcp_servers()` — only component requiring code changes; add optional `env` dict entry for `MIC_TRANSFORMER_API_URL` (currently already wired, minor enhancement)
2. `config.py` — add `MIC_TRANSFORMER_API_URL` env var mapping; single line addition
3. mic_transformer `config/*.yml` files on VM — the primary deployment prerequisite; must contain production DB, GCS, Google Drive, and CrystalPM credentials
4. mic_transformer `.venv` on VM — must have `mcp[cli]~=1.26.0` installed
5. All other bot components (`app.py`, `handlers.py`, `queue_manager.py`, `worktree.py`, `progress.py`) — no changes required

### Critical Pitfalls

See [PITFALLS.md](PITFALLS.md) for the full 12-pitfall inventory with detection signals, recovery costs, and phase assignments.

1. **env dict replaces rather than extends subprocess environment** — passing any `env` field to `McpStdioServerConfig` may replace the entire inherited process environment (Python `subprocess.Popen` behavior), causing all credential lookups to fail silently while the server reports "connected." Prevention: if adding env vars, always merge with `{**os.environ, "EXTRA_VAR": "value"}`; verify by testing one tool from each credential category immediately after wiring.

2. **systemd EnvironmentFile syntax silently drops variables** — `export KEY=val`, `$VAR` interpolation, and backtick substitution are all invalid in systemd's `EnvironmentFile` parser and are silently dropped (not flagged as errors). Works locally under `python-dotenv` but breaks under systemd. Prevention: audit `/home/bot/.env` for non-`KEY=VALUE` lines; validate with `sudo -u bot env | grep EXPECTED_VAR` on the VM after deployment.

3. **MCP server startup timeout kills the session** — the Claude Agent SDK has a fixed 60-second connection timeout for MCP servers. mic_transformer's heavy dependency tree (boto3, google-cloud-storage, SQLAlchemy, Prefect client) may exceed this on a resource-constrained GCP VM, especially cold (no `.pyc` cache). Prevention: benchmark `time /path/to/venv/bin/python server.py` on the actual VM; lazy-import heavy modules inside tool functions rather than at the module level if startup exceeds 30 seconds.

4. **Wrong fastmcp package installed** — the server imports `from mcp.server.fastmcp import FastMCP` (FastMCP 1.0 bundled inside the official `mcp` PyPI package). The standalone `fastmcp` package on PyPI (jlowin/Prefect project, version 3.x) is a different project entirely. Installing standalone `fastmcp` would be unused and risks import shadowing. Prevention: install `mcp[cli]~=1.26.0` only; verify with `python -c "from mcp.server.fastmcp import FastMCP; print('OK')"`.

5. **stdout pollution corrupts the JSON-RPC protocol stream** — MCP stdio uses stdout exclusively for JSON-RPC messages. Any `print()` call in the server or its dependencies corrupts the stream and kills the connection. Prevention: audit with `grep -r "print(" server.py tools/`; configure all Python logging to write to stderr only.

## Implications for Roadmap

The integration should proceed in four phases ordered by credential complexity and operational blast radius. Total code changes are under 10 lines across two files. The phases differ primarily in which VM prerequisites must be verified before each phase's tools can be tested.

### Phase 1: VM Validation and MCP Server Wiring

**Rationale:** Environment issues under systemd are the most common MCP integration failure mode and must be caught before any feature testing. A single broken env variable silently disables ~80% of tools. This phase has zero production risk and ends with one confirmed working tool call.

**Delivers:** End-to-end verified MCP connectivity; `deploy_version` tool returns the production API version from a Slack message. All credential infrastructure confirmed working.

**Addresses (features):** `deploy_version` (zero-risk connectivity proof); at least one read-only status tool as GCS/DB connectivity validation.

**Avoids (pitfalls):** Pitfall 2 (systemd EnvironmentFile syntax), Pitfall 5 (wrong fastmcp package), Pitfall 6 (startup timeout), Pitfall 9 (stdout pollution) — all must be caught here.

**Tasks (in order):**
- Install `mcp[cli]~=1.26.0` in `/home/bot/mic_transformer/.venv`; verify with import test
- Confirm `config/*.yml` files exist with production credentials for DB, GCS, GDrive, CrystalPM
- Audit `/home/bot/.env` for systemd-incompatible syntax; fix any `export` or interpolation lines
- Add `MIC_TRANSFORMER_API_URL` to `config.py` (single line)
- Update `_build_mcp_servers()` to include optional `env` dict (minimal change)
- Benchmark MCP server cold-start time on VM; lazy-import boto3/GCS if needed
- End-to-end test: send "check deploy version" to Slack channel; confirm tool returns real data

### Phase 2: Read-Only Status and Storage Tools

**Rationale:** The 20+ read-only tools covering Nicole's primary daily queries have no blast radius and validate that all four credential categories (GCS, S3, Google Drive, PostgreSQL) work correctly. This builds confidence before any write operations are attempted.

**Delivers:** Nicole can ask "what's the VSP status for today?" or "did the EyeMed PDF arrive for this location?" from Slack and receive real pipeline state data.

**Addresses (features):** All 11 Module 1 status/audit tools, Module 5 storage tools (5 read-only), `check_pipeline_status`, `pipeline_stage_view`, `gdrive_audit`, `provider_revenue`, `ocea_health_check`.

**Avoids (pitfall 1):** Test one tool from each credential category (GCS: `list_gcs_aiout`; S3: `list_s3_remits`; GDrive: `gdrive_audit`; DB: `provider_revenue`; SSH: `check_prefect_flow_status`) to verify env inheritance is working across all pathways.

### Phase 3: API-Triggered and Prefect Tools

**Rationale:** Extraction, reduction, benefits fetch, and Prefect flow status tools mutate state but do so through validated production infrastructure. The Flask API validates inputs before dispatching to Celery workers; Prefect provides its own retry and audit trail. These are safer than local subprocess execution.

**Delivers:** Full daily pipeline workflow operable from Slack: check status, trigger VSP/EyeMed extraction, trigger reduction, check and diagnose Prefect flow status. Benefits fetch, Azure mirror, and IVT audit tools also covered.

**Addresses (features):** Module 2 (extraction), Module 3 (reduction), Module 8 (PDF ingestion), Module 9 (benefits fetch — polls up to 10 min), Module 11 (azure mirror audit and trigger), Module 12 (IVT ingestion audit).

**Avoids (pitfall 7):** Benefits fetch polls for up to 10 minutes. Verify SuperBot's `run_agent_with_timeout` accommodates this duration before declaring this phase complete.

### Phase 4: Subprocess-Based Mutating Tools

**Rationale:** Posting prep and autopost tools run local Python subprocesses that interact with Revolution EMR and modify GCS/Google Drive state. The `dry_run=True` defaults provide a safety net, but these require the most deliberate testing. Autopost is the highest-value and highest-risk capability in the entire tool suite.

**Delivers:** Nicole can trigger posting prep (GDrive upload, task sheet generation) and eventually run autoposts from Slack. Full operational automation pipeline achievable without opening a laptop.

**Addresses (features):** Module 4 posting prep (3 tools), `vsp_autopost`, `eyemed_autopost`, `clear_pipeline`.

**Avoids (pitfall 3 and 10):** Audit subprocess calls in posting tools for `os.chdir()` usage; verify tools use unique temp paths per invocation to avoid session collision. Require explicit "live run" instruction before any `dry_run=False` autopost test.

### Phase Ordering Rationale

- Phase 1 before everything: systemd environment propagation must be verified before feature testing begins; a broken env silently breaks 80% of tools and is harder to diagnose once feature testing has started
- Read-only (Phase 2) before write (Phases 3-4): validates all four credential pathways with zero blast radius; failing writes are harder to diagnose than failing reads
- API-mediated writes (Phase 3) before subprocess writes (Phase 4): production API provides input validation and error reporting that local subprocesses do not
- `remit_crawler` deferred beyond Phase 4: headless Chrome on GCP VM is an unknown; do not block v1.2 on this; interim path is SSH to production server

### Research Flags

Phases needing deeper research during planning:
- **Phase 3 (Benefits fetch timeout):** The 10-minute Prefect polling in benefits fetch tools needs explicit verification against SuperBot's session timeout configuration. The `run_agent_with_timeout` default may need adjustment.
- **Phase 4 (Revolution EMR subprocess in dry_run):** The behavior of `run_revolution_poster.py` in dry_run mode should be manually tested on the VM before wiring to Slack to understand its output and failure modes.

Phases with standard patterns (can skip deeper research):
- **Phase 1 (VM wiring):** All patterns are well-documented in the research files; `mcp[cli]` install is a single command; systemd env validation is standard.
- **Phase 2 (Read-only tools):** All 20+ tools have been fully analyzed from source; credential paths are documented in FEATURES.md and ARCHITECTURE.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | `McpStdioServerConfig` fields verified directly from installed `claude_agent_sdk/types.py`; version compatibility verified from installed packages; import path for FastMCP confirmed from mic-transformer server.py source |
| Features | HIGH | All 35+ tools analyzed from direct source code inspection of mic-transformer MCP server modules; no assumptions; credential dependencies mapped per-tool |
| Architecture | HIGH | Execution chain verified from SDK `subprocess_cli.py` source; `os.chdir()` subprocess isolation is OS-level guarantee; credential loading via YAML config files verified from tool source code |
| Pitfalls | HIGH | Critical pitfalls backed by official SDK GitHub issues (#573), official FastMCP GitHub issues (#399, #1311), MCP Python SDK issues (#671), and systemd documentation; not community speculation |

**Overall confidence:** HIGH

### Gaps to Address

- **Chrome/Chromium on GCP VM for remit_crawler:** Unknown whether headless browser is installed or reliably usable on the VM. Check during Phase 1 VM audit; if not present, keep deferred and document SSH workaround.
- **Prefect API credentials (`shen:tofu` basic auth):** Hardcoded in MCP tools. Verify this account remains active and is reachable from the GCP VM's network before Phase 3.
- **Revolution EMR credentials on VM:** `vsp_autopost` and `eyemed_autopost` require Revolution EMR credentials in mic_transformer config. Verify these are present in the VM's mic_transformer clone before beginning Phase 4 testing.
- **VM compute sizing:** PITFALLS.md flags e2-small/medium as potentially insufficient for MCP startup under memory pressure. If the Phase 1 cold-start benchmark exceeds 30 seconds, upgrade proactively to e2-medium before lazy-import optimization.
- **`prod-ivt` DB access from VM:** `ivt_ingestion_audit` (Module 12) accesses the production `prod-ivt` database. Confirm the GCP VM has network access to `34.136.128.245` and that the `ivt_app_user` credentials are in the mic_transformer clone. Given the global CLAUDE.md warning about this database, document that this tool is read-only before enabling it.

## Sources

### Primary (HIGH confidence)
- Installed `claude_agent_sdk` package source (`types.py`, `subprocess_cli.py`) — `McpStdioServerConfig` definition and CLI spawning behavior
- mic-transformer MCP server source (`.claude/mcp/mic-transformer/server.py`, all 13 tool modules, `common.py`) — complete feature inventory and credential patterns
- [Claude Agent SDK MCP documentation](https://platform.claude.com/docs/en/agent-sdk/mcp) — 60-second connection timeout, env field behavior
- [Claude Agent SDK Python GitHub Issue #573](https://github.com/anthropics/claude-agent-sdk-python/issues/573) — confirms subprocess environment inheritance behavior
- [MCP Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk) — FastMCP 1.0 bundled in `mcp` package history
- [FastMCP GitHub Issue #399](https://github.com/jlowin/fastmcp/issues/399) — stdio initialize succeeds, subsequent requests crash (known issue)
- [FastMCP GitHub Issue #1311](https://github.com/jlowin/fastmcp/issues/1311) — subprocess cleanup issues in stdio mode
- [MCP Python SDK Issue #671](https://github.com/modelcontextprotocol/python-sdk/issues/671) — stdio tool execution hangs in external scripts

### Secondary (MEDIUM confidence)
- [Baeldung: systemd environment variables](https://www.baeldung.com/linux/systemd-services-environment-variables) — EnvironmentFile syntax restrictions; corroborated by systemd man page
- [Claude Code in Slack official docs](https://code.claude.com/docs/en/slack) — competitor feature comparison baseline
- [GitHub Copilot coding agent in Slack](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-slack) — competitor feature comparison baseline
- [Anthropic long-running agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — patterns for production agent deployments

### Tertiary (informational only)
- [FastMCP PyPI page](https://pypi.org/project/fastmcp/) — confirms standalone fastmcp is a separate project from `mcp.server.fastmcp`
- [Kilo for Slack feature page](https://kilo.ai/features/slack) — competitor feature comparison

---
*Research completed: 2026-03-23*
*Ready for roadmap: yes*
