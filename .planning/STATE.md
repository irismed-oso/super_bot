# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.
**Current focus:** Milestone v1.2: MCP Parity

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-23 — Milestone v1.2 started

## Accumulated Context

### Decisions

- Roadmap: Claude Agent SDK (not raw subprocess) — avoids documented TTY-hang bug; async-only, required for lazy listener pattern
- Roadmap: Socket Mode (no public URL) — eliminates need for load balancer, TLS, or ingress on the VM
- v1.2: mic-transformer MCP server runs locally on VM as stdio subprocess — no network travel, uses existing clone at /home/bot/mic_transformer
- v1.2: Direct MCP wiring (not Flask bridge) — simpler, standard pattern, Claude Agent SDK handles stdio MCP natively

### Pending Todos

None yet.

### Blockers/Concerns

- mic-transformer .venv on VM needs `mcp` and `fastmcp` packages (may not be installed yet)
- MCP server tools need cloud credentials (GCS, S3, Azure, Prefect, Revolution EMR) available in the subprocess environment
- MCP server does `os.chdir(PROJECT_ROOT)` which could affect CWD if not isolated properly

## Session Continuity

Last session: 2026-03-23
Stopped at: Defining v1.2 requirements
Resume file: None
