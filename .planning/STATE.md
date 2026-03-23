# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.
**Current focus:** Milestone v1.2: MCP Parity (Phase 5: VM Validation and MCP Wiring)

## Current Position

Phase: 5 of 7 (VM Validation and MCP Wiring) -- COMPLETE
Plan: 2 of 2 in current phase
Status: Phase complete
Last activity: 2026-03-23 — Completed 05-02 (VM deployment + MCP connectivity validation)

Progress: [#############.......] 65% (v1.0 phases 1-2 complete, phase 3 near done, phase 5 complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 14
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 4/4 | — | — |
| 2 | 3/3 | — | — |
| 3 | 4/5 | — | — |
| 4 | 0/TBD | — | — |
| 5 | 2/2 | 7min | 3.5min |

## Accumulated Context

### Decisions

- v1.2: mic-transformer MCP server runs locally on VM as stdio subprocess — no network travel, uses existing clone at /home/bot/mic_transformer
- v1.2: Direct MCP wiring (not Flask bridge) — simpler, standard pattern, Claude Agent SDK handles stdio MCP natively
- v1.2: Install `mcp[cli]~=1.26.0` only (NOT standalone `fastmcp`) — server imports from `mcp.server.fastmcp`, standalone package is a different project
- v1.2: Read-only tools before mutation tools — validates all credential pathways with zero blast radius before write operations
- v1.2: MIC_TRANSFORMER_MCP_DISABLED defaults to False (enabled by default when path exists), checked before path detection for clean short-circuit
- v1.2: No env field on mic-transformer MCP server config — subprocess inherits parent env, credentials come from config/*.yml
- v1.2: No pre-warming needed — cold-start benchmark 1.273s on VM, well under 60s SDK timeout
- v1.2: 23 config yml files (not 7) needed on VM for full mic-transformer MCP operation

### Pending Todos

None yet.

### Blockers/Concerns

- ~~MCP server cold-start time on VM must be under 60 seconds (SDK timeout)~~ RESOLVED: 1.273s
- ~~systemd EnvironmentFile syntax must be audited~~ RESOLVED: clean, no issues
- Benefits fetch (MTTL-07) polls Prefect for up to 10 minutes — verify SuperBot session timeout accommodates this in Phase 7
- Revolution EMR credentials must be present in mic_transformer config on VM — Phase 7 prerequisite

## Session Continuity

Last session: 2026-03-23
Stopped at: Completed 05-02-PLAN.md (Phase 5 complete)
Resume file: None
