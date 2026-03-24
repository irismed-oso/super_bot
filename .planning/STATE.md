# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Nicole can ask the bot to do anything on mic_transformer through Slack and it just does it — writes code, runs scripts, debugs issues, deploys — with full autonomy and persistent awareness.
**Current focus:** Milestone v1.2: MCP Parity (Phase 7: Mutation Tools)

## Current Position

Phase: 6 of 7 (Read-Only Status and Storage Tools) -- COMPLETE
Plan: 2 of 2 in current phase
Status: Phase complete
Last activity: 2026-03-23 — Completed 06-02 (Extended credential pathway validation)

Progress: [###############.....] 75% (v1.0 phases 1-2 complete, phase 3 near done, phases 5-6 complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 16
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
| 6 | 2/2 | — | — |

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
- v1.2: All read-only credential pathways confirmed working (GCS, S3, PostgreSQL x3, Google Drive); SSH publickey denied for ansible user is non-blocking
- v1.2: No code changes needed for Phase 6 -- all tools work with existing VM configuration from Phase 5

### Pending Todos

None yet.

### Blockers/Concerns

- ~~MCP server cold-start time on VM must be under 60 seconds (SDK timeout)~~ RESOLVED: 1.273s
- ~~systemd EnvironmentFile syntax must be audited~~ RESOLVED: clean, no issues
- Benefits fetch (MTTL-07) polls Prefect for up to 10 minutes — verify SuperBot session timeout accommodates this in Phase 7
- Revolution EMR credentials must be present in mic_transformer config on VM — Phase 7 prerequisite

## Session Continuity

Last session: 2026-03-24
Stopped at: Completed 06-02-PLAN.md (Phase 6 complete)
Resume file: None
