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


## v1.5 -- Nicole-Ready Operations (Phases 11-13, shipped 2026-03-25)

**Goal:** Nicole can check status, trigger crawls, and get clear feedback — all without hitting timeouts or confusing error messages.

**Shipped:**
- Fast-path crawl trigger: "crawl eyemed DME 03.20" triggers Prefect deployment in <5 seconds, no agent session
- Fast-path status: "status on DME eyemed 03.16 to today" runs status script with location/date filters
- Batch crawl: "crawl all sites for 03.20" triggers all 23 Prefect deployments in parallel
- Background task monitoring with progress updates every 2.5 min and final summary
- Background tasks don't block agent queue — other tasks can run while crawls are in progress
- Error UX: timeout messages include what was attempted + suggested next action
- Error messages distinguish timeout vs failure vs still-running
- "Are you broken?" returns actual task status without spawning a new agent session
- All fast-path responses edit "Working on it." message in-place

**Stats:** 3 phases, 3 plans

---


## v1.6 -- Progress Heartbeat (Phase 14, shipped 2026-03-25)

**Goal:** During long sessions, the bot posts periodic progress updates so users never wonder if it's stuck.

**Shipped:**
- Heartbeat timer edits progress message every 3 min (first tick at 1 min) with last activity, turn count, elapsed time
- Heartbeat fires independently of agent tool use — pure asyncio timer
- On normal completion: progress message edited to "Completed in Xm Ys" before result posts
- On timeout/cancel: heartbeat stops cleanly with no further edits
- Format: ":hourglass: Still working... [Activity] | Turn X/25 | Ym Zs"

**Stats:** 1 phase, 1 plan

---


## v1.7 -- Deploy & Verify (Phases 15-16, shipped 2026-03-25)

**Goal:** Get v1.4-v1.6 features deployed and verified on the production VM.

**Shipped:**
- Reusable `scripts/deploy.sh` — one-command deploy (push, pull, deps, restart, health-check)
- Deploy script with `--skip-push`, `--skip-deps`, `--branch` flags for flexibility
- Live verification: digest changelog posting at 08:00 daily
- Live verification: fast-path commands actively used by Nicole (crawl + status)
- Live verification: heartbeat ticking during real sessions (3m 9s, 4m 46s elapsed)

**Stats:** 2 phases, 2 plans

**Known issues:**
- `os.getlogin()` fails under systemd (no TTY) — digest crosscheck degrades gracefully
- VRFY-03 (batch crawl monitor) not yet triggered by user — single crawl works

---

