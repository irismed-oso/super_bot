# Phase 6: Read-Only Status and Storage Tools - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate that all read-only MCP tools return real data when invoked through SuperBot. This covers status checks (VSP, EyeMed), storage browsing (S3, GCS), pipeline audits, Azure mirror status, IVT ingestion health, Prefect flow status, Google Drive audit, and crawler location listing. No code changes to the tools themselves -- this is purely validation and credential/network fixing.

</domain>

<decisions>
## Implementation Decisions

### Validation method
- Test via direct agent calls on the VM (run_agent()) -- faster, no Slack bot filter issues
- Same approach as Phase 5's successful pipeline status test
- No Slack @mention testing required for this phase (proven in Phase 5)

### Test coverage
- Claude's discretion on balance between testing every tool vs one-per-credential-category
- At minimum, one tool per credential pathway (GCS, S3, GDrive, PostgreSQL) must be confirmed working

### Failure handling
- Claude's discretion: fix immediately if straightforward (credential config, network rule), defer if complex
- Phase passes if core tools work (VSP/EyeMed status, pipeline audit)
- Document any tools that don't work and why

### Test data
- Claude picks the location with the most complete pipeline data for testing
- Beverly is a known working location from Phase 5

### Credential gaps
- Unknown which credential paths work beyond GCS (confirmed in Phase 5)
- Test each path and fix as we go
- GDrive OAuth may need special handling on the VM

### Claude's Discretion
- Which tools to test and in what order
- Whether to test all 20+ tools or a representative subset
- How to handle tools that fail (fix vs defer)
- Test location selection

</decisions>

<specifics>
## Specific Ideas

- Phase 5 proved: MCP wiring works, cold-start is fast (1.3s), GCS credentials work, network reaches production API
- Direct agent call pattern: `run_agent("check X for location Y today", session_id=None, max_turns=5)`
- All config/*.yml files already on VM (23 files copied in Phase 5)

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 06-read-only-status-and-storage-tools*
*Context gathered: 2026-03-23*
