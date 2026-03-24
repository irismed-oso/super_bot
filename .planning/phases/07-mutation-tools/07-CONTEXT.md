# Phase 7: Mutation Tools - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate that all write/trigger MCP tools work through SuperBot -- extraction, reduction, autopost (dry_run), posting prep, PDF ingestion, Azure mirror sync, benefits fetch, and page requeue. These tools have production impact and require careful safety controls.

</domain>

<decisions>
## Implementation Decisions

### Safety controls
- Claude's discretion on which tools to run live vs dry_run vs skip
- Autopost tools: default dry_run=True provides built-in safety
- Extraction/reduction: API validates inputs, lower risk
- Upload tools (posting_prep, ingest_pdf): Claude assesses risk per tool

### Test scope
- Claude's discretion on coverage (all 8 tools vs representative subset)
- Direct agent calls on VM (same pattern as Phase 5/6)
- Use locations with known data for best results

### Autopost handling
- Claude decides: dry_run only vs one live test based on data availability
- dry_run=True is the default, safe to test
- Live posting only if Claude determines it's safe with available data

### Benefits fetch
- Claude decides: test or skip based on feasibility
- 10-minute polling vs 10-minute session timeout is a known risk
- SSH publickey issue from Phase 6 may affect Prefect-dependent flows

### Claude's Discretion
- All safety/scope/mode decisions delegated to Claude
- Fix credential issues encountered (same as Phase 6)
- Document any tools that don't work and why
- Phase passes if core mutation tools are confirmed callable

</decisions>

<specifics>
## Specific Ideas

- Phase 6 confirmed: all credential paths work except SSH publickey (non-blocking)
- Same test pattern: direct agent calls via run_agent() on VM
- Autopost dry_run is the safest proof of mutation tool functionality
- Benefits fetch may need increased max_turns or timeout

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 07-mutation-tools*
*Context gathered: 2026-03-24*
