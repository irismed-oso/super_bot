# Milestones

## v1.0 -- Core Bot (Phases 1-3, shipped 2026-03-20)

**Goal:** GCP VM running a Slack bot that triggers Claude Code sessions and reports results.

**Shipped:**
- GCP VM provisioned with systemd service, auto-restart, journald logging
- Slack bot with Socket Mode, lazy listener, event dedup, access control
- Claude Agent SDK with session management, timeout, queue serialization
- End-to-end: @mention triggers Claude session, progress/results posted to thread
- Git worktree isolation, branch/commit/PR operations

**Stats:** 3 phases, 12 plans, 1,557 LOC Python

## v1.1 -- Capability Parity (shipped 2026-03-21)

**Goal:** Linear and Sentry MCP integration, multi-repo read access, custom skills.

**Shipped:**
- Linear MCP and Sentry MCP wired into Claude Agent SDK sessions
- Multi-repo read access (all 4 IrisMed repos)
- Custom operational skills executable via Slack
- Daily activity digest

## v1.2 -- MCP Parity (Phases 5-7, shipped 2026-03-24)

**Goal:** SuperBot has direct access to all mic-transformer MCP tools locally on the VM.

**Shipped:**
- mic-transformer MCP server wired as stdio subprocess (1.3s cold-start)
- 35+ operational tools across 13 modules validated
- All 7 credential pathways confirmed: GCS, S3, PostgreSQL (x3), Google Drive, SSH
- Read-only tools: vsp_status, eyemed_status, pipeline_audit, azure_mirror_audit, ivt_ingestion_audit, gdrive_audit, list_crawler_locations, list_s3_remits, list_gcs_aiout, check_prefect_flow_status
- Mutation tools: vsp_extract, reduce_aiout, vsp_autopost (dry_run), posting_prep, ingest_pdf, azure_mirror_trigger, requeue_missing_pages
- MIC_TRANSFORMER_MCP_DISABLED feature flag for troubleshooting
- Full mic_transformer requirements.txt installed on VM

**Stats:** 3 phases, 6 plans, 6 days (Mar 18-24)

**Known gap:** MTTL-07 (vision_benefits_fetch) skipped due to 10-min polling vs 10-min session timeout conflict

## v1.3 -- Response Timing (Phase 8, shipped 2026-03-24)

**Goal:** Show elapsed time in bot's final Slack reply for task duration visibility.

**Shipped:**
- Elapsed time footer appended to completion and error messages (e.g. "Completed in 2m 34s")
- Fast-path command system for bypassing agent pipeline on common queries
- EyeMed scan status script (eyemed_scan_status.py) for instant status checks
- Multi-channel support (ALLOWED_CHANNEL accepts comma-separated IDs)
- Timeout partial text preservation (shared_partials survives cancellation)
- Crawler exit code fix (0=success, 1=error, 2=no files)

**Stats:** 1 phase, 1 plan

## v1.4 -- Digest Changelog (Phases 9-10, shipped 2026-03-24)

**Goal:** Daily digest shows a changelog of git commits and PRs the bot created, so the team sees what actually changed each day.

**Shipped:**
- Post-session git activity capture (commits with hash/message/repo/branch/files, PRs with URL/title/repo)
- Deduplication prevents re-logging on thread follow-ups
- Daily digest changelog section with commits/PRs grouped by repository
- Git log cross-check at digest build time catches missed commits (crash recovery)
- Author-filtered scan, single-repo header optimization, recovered commit markers
- Slack mrkdwn PR hyperlinks, 15-commit cap with overflow

**Stats:** 2 phases, 2 plans, 497 LOC Python (bot/git_activity.py + bot/digest_changelog.py)

---

