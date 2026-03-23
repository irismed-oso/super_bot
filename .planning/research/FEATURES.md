# Feature Landscape

**Domain:** Slack-integrated autonomous coding agent (GCP VM + Claude Code CLI)
**Researched:** 2026-03-23 (v1.2 MCP Parity update, appended to 2026-03-18 baseline)
**Confidence:** HIGH -- all v1.2 findings derived from direct source code analysis of mic-transformer MCP server

---

## Feature Landscape (v1.0/v1.1 Baseline)

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| @mention trigger in Slack channel | Every Slack bot works this way; it's the entry point | LOW | Must work in channel (not DM). Claude Code in Slack official docs confirm channel-only pattern. |
| Thread-scoped context | Users expect the bot to read the thread before acting, not just the @mention message | LOW | All major agents (Kilo, Copilot, Claude) pull full thread history. Critical for multi-turn tasks. |
| Streamed / incremental progress updates | Long-running tasks feel like a black box without updates; users assume the bot checks in | MEDIUM | Post "working on it" or step-by-step updates as Claude Code runs. Prevents users from retrying. |
| Completion notification with summary | Users expect to be @mentioned when the task is done with what happened | LOW | Standard pattern across Devin, Kilo, Copilot, Claude Code in Slack. |
| Git operations: branch, commit, push | This is a coding agent -- version control is assumed | LOW | Claude Code CLI natively supports git. |
| PR creation from Slack | Users treat "do X and open a PR" as a single natural command | MEDIUM | All major agents (Kilo, Copilot, Claude Code in Slack) support this. |
| Code reading and Q&A about the repo | "What does X function do?" is the most common first use case | LOW | Claude Code CLI reads files natively; no extra work needed. |
| Script and command execution | Running Prefect flows, tests, operational scripts is core to this project's value | MEDIUM | VM shell access; Claude Code CLI handles subprocess execution. |
| Error reporting back to Slack | If the bot fails, the channel needs to see why -- silently broken is worse than broken | LOW | Post error messages and stack traces as Slack replies. |
| Named-user access control | Small team means only Nicole/Han/named users should trigger the bot | LOW | Allowlist by Slack user ID checked before processing any message. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Persistent project memory (CLAUDE.md + git history) | Bot builds accumulated awareness of mic_transformer instead of starting cold each time | MEDIUM | Claude Code memory system + project CLAUDE.md. Far better than stateless agents. Devin Wiki is the commercial equivalent. |
| Mic_transformer-specific operational commands | "Run the VSP reconciliation flow" works without explaining what that means | LOW | Achieved naturally via Claude Code reading the codebase and CLAUDE.md. No extra code. |
| Isolated task workspaces per job | Each Slack task runs in its own git worktree so concurrent tasks don't stomp each other | HIGH | Sleepless-agent pattern. Requires task queue + workspace manager on the VM. Significant reliability win. |
| Task queue with status slash commands | `/status`, `/cancel` for in-flight tasks -- know what's running without asking | MEDIUM | SQLite-backed queue. Sleepless-agent implements this. Prevents duplicate work. |
| Daily digest / activity report | "Here's what I did today" posted to channel on a schedule | LOW | Cron job reading git log + task history. Trust-building for autonomous agent. |
| Automatic test running after code changes | Bot runs tests before reporting done, surfaces failures in Slack | MEDIUM | Claude Code can invoke pytest; pass/fail posted to thread. Reduces review burden. |
| Deployment from Slack | "Deploy to staging" triggers actual deploy workflow from the VM | HIGH | Requires deploy scripts already in mic_transformer. High value but high blast radius. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Approval gates for every destructive action | "Safety first" -- humans want to confirm before the bot does anything risky | PROJECT.md explicitly rules this out; approval gates defeat the value of full autonomy for a trusted small team; adds latency and friction to every task | Trust the team + channel visibility. Everyone sees what was asked and done. Use git history as the audit trail. |
| DM-based interaction | Users may want private tasks | DMs hide what the bot is doing from teammates; kills team awareness, which is a core design goal | Channel mentions only. If privacy is needed, use a private channel. |
| Web UI / dashboard | Nice to visualize agent activity | Duplicates Slack; adds a whole new surface to build and maintain | Slack is the dashboard. Post status, results, and daily digests there. |
| Multi-repo support | Teams often work across repos | Dramatically increases complexity of repo selection, context, and security surface | mic_transformer only for v1. Pin scope. |
| Per-user sandboxed environments | Enterprise agents give each user their own environment | Unnecessary overhead for a 2-person team; one shared VM and repo is simpler and sufficient | Single shared VM with git worktrees for task isolation. |
| Real-time token-by-token streaming to Slack | "Show me Claude thinking live" | Slack rate limits will get the bot banned (60 messages/min per channel); streaming at token level is unusable in practice | Post milestone updates (started, tool calls, done). Update a single message via edit rather than spamming new messages. |
| Webhook-based retry loops | Automatically retry every failed task | Retries on bad prompts waste Claude tokens; retries on broken environments loop indefinitely | Report failures clearly. Let humans decide to retry or rephrase. |
| Full chat assistant mode (non-coding Q&A) | "Ask the bot anything" | Dilutes the product; users start treating it as a general chatbot instead of a coding agent; hard to distinguish from Slack's built-in Claude app | Scope to coding and operational tasks on mic_transformer. |

---

## v1.2 MCP Parity: mic-transformer MCP Tool Inventory

### Complete Tool Catalog (35+ tools across 13 modules)

Source: Direct code analysis of `/mic_transformer/.claude/mcp/mic-transformer/` (all 13 tool modules).

#### Module 1: Status (11 tools) -- READ-ONLY

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `vsp_status` | VSP processing status across all locations for a date | High | GCS, S3, GDrive, DB |
| `eyemed_status` | EyeMed processing status across all locations for a date | High | GCS, S3, GDrive, DB |
| `check_prefect_flow_status` | Check Prefect flow runs via SSH + journalctl parsing | Med | SSH to production (ansible@136.111.85.127) |
| `pipeline_audit` | Query vsp_processing_audit_logs for flow run history | Med | DB (IrisMedAppDB) |
| `pipeline_stage_view` | Stage-by-stage pipeline progress for one location/date | High | GCS, S3, GDrive, DB |
| `get_prefect_logs` | Fetch Prefect flow run logs for debugging | Med | Prefect API (HTTP auth) + DB |
| `eyemed_crawler_audit` | Audit EyeMed crawler S3 output + audit logs | High | S3, DB |
| `eyemed_crawler_detail` | Detailed per-location crawler result view | Med | DB |
| `eyemed_status_range` | EyeMed status grid across a date range | High | GCS, GDrive, DB |
| `eyemed_scan_results` | Query eyemed_crawler_scan_results table | Med | DB |
| `for_eyes_autopost_analysis` | Analyze For Eyes posting results with ZER detection | High | GCS, DB |

#### Module 2: Extraction (3 tools) -- WRITE/MUTATING

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `vsp_extract` | Trigger VSP Gemini AI extraction via production API | Med | Production API (HTTP to 136.111.85.127:8080) |
| `eyemed_extract` | Trigger EyeMed Gemini AI extraction via production API | Med | Production API |
| `requeue_missing_pages` | Requeue incomplete extractions via production API | Med | Production API |

These make HTTP POST requests to the production Flask API which dispatches to Celery workers.

#### Module 3: Reduction (2 tools) -- WRITE/MUTATING

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `reduce_aiout` | Reduce JSON files to AIOUT for one location | Med | GCS (pre-check), Production API |
| `reduce_all_vsp` | Reduce all VSP locations with complete extraction | Med | Production API |

Pre-checks GCS for json_files completeness before triggering API. Longer timeouts (5-10 min).

#### Module 4: Posting (5 tools) -- WRITE/MUTATING (HIGHEST RISK)

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `vsp_autopost` | Post VSP payments to Revolution EMR | High | GCS, Revolution EMR credentials (subprocess) |
| `eyemed_autopost` | Post EyeMed payments to Revolution EMR | High | GCS, Revolution EMR credentials (subprocess) |
| `posting_prep` | Upload remits to GDrive, generate task sheets | High | GCS, S3, GDrive |
| `eyemed_posting_prep` | EyeMed posting prep for one location over date range | High | GCS, GDrive, DB |
| `eyemed_posting_prep_all` | Batch EyeMed posting prep for ALL locations | High | GCS, GDrive, DB |

Autopost tools default to `dry_run=True` for safety. They run subprocess calls to `run_revolution_poster.py`.

#### Module 5: Storage (6 tools) -- MIXED (mostly READ, one WRITE)

| Tool | Purpose | Read/Write | Credentials Required |
|------|---------|------------|---------------------|
| `list_s3_remits` | List remittance PDFs in S3 | READ | S3 (AWS) |
| `list_gcs_aiout` | List AIOUT files in GCS | READ | GCS |
| `check_pipeline_status` | Full 4-stage pipeline status with color coding | READ | S3, GCS, GDrive |
| `gcs_inventory` | All files in GCS for a location across date range | READ | GCS |
| `list_recent_uploads` | Recently uploaded AIOUT files | READ | GCS |
| `clear_pipeline` | Delete pipeline artifacts for re-processing | WRITE (DESTRUCTIVE) | GCS, GDrive, DB, subprocess |

`clear_pipeline` defaults to `dry_run=True` and calls `scripts/reset_pipeline.py`.

#### Module 6: Crawler (2 tools) -- WRITE/MUTATING

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `remit_crawler` | Trigger insurance portal PDF download | High | Insurance portal credentials, S3, GCS, GDrive, browser |
| `list_crawler_locations` | List available crawler locations | Low | None |

Crawler runs subprocess (`vsp_1_crawler.py` or `eyemed_crawler.py`). Needs Chrome/Chromium for headless mode.

#### Module 7: Google Drive (1 tool) -- READ-ONLY

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `gdrive_audit` | Audit GDrive folders for remit file completeness | High | GDrive API (service account), GCS |

#### Module 8: Ingestion (1 tool) -- WRITE/MUTATING

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `ingest_pdf` | Upload manually-obtained PDF into pipeline | Med | Production API |

#### Module 9: Benefits (3 tools) -- WRITE/MUTATING

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `vision_benefits_fetch` | Fetch VSP benefits via Prefect deployment | High | Prefect API (HTTP auth shen:tofu) |
| `eyemed_benefits_fetch` | Fetch EyeMed benefits via Prefect deployment | High | Prefect API |
| `medical_benefits_fetch` | Fetch Availity medical benefits via Prefect | High | Prefect API |

All three trigger Prefect deployments and poll until completion (up to 10 min).

#### Module 10: Deploy (1 tool) -- READ-ONLY

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `deploy_version` | Check production deploy version via healthcheck | Low | Production API (HTTP GET) |

#### Module 11: Azure Mirror (3 tools) -- MIXED

| Tool | Purpose | Read/Write | Credentials Required |
|------|---------|------------|---------------------|
| `azure_mirror_audit` | Check CrystalPM mirror DB freshness (24 locations) | READ | PostgreSQL (crystalpm-mirror DB via psycopg2) |
| `azure_mirror_trigger` | Trigger Hop 1 sync via Prefect | WRITE | SSH + Prefect API (via SSH tunnel) |
| `azure_mirror_run_status` | Check recent mirror flow run statuses | READ | SSH + Prefect API |

#### Module 12: IVT Ingestion (1 tool) -- READ-ONLY

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `ivt_ingestion_audit` | Audit IVT data ingestion health (Prefect + prod-ivt DB) | High | SSH + Prefect API, PostgreSQL (prod-ivt DB) |

#### Module 13: Analytics (1 tool) -- READ-ONLY

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `provider_revenue` | Provider-level revenue from AIOUT remittance data | Med | DB (IrisMedAppDB via SQLAlchemy) |

#### Module 14: Monitoring (1 tool) -- READ (unless dry_run=False)

| Tool | Purpose | Complexity | Credentials Required |
|------|---------|------------|---------------------|
| `ocea_health_check` | OCEA daily health check for expected Prefect flows | Med | DB (prefect_log_jobs) |

---

## v1.2 MCP Feature Classification

### Table Stakes for MCP Parity

Features SuperBot MUST expose to achieve parity with local Claude Code MCP usage.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| All status/audit tools (11+ read-only) | Nicole's primary workflow starts with "what's the status?" | Med | Needs GCS, S3, GDrive, DB credentials on VM |
| Extraction triggers (vsp_extract, eyemed_extract, requeue) | Daily workflow: check status then trigger extraction | Med | Just HTTP POST to production API |
| Reduction triggers (reduce_aiout, reduce_all_vsp) | Daily workflow: reduce after extraction completes | Med | GCS pre-check + HTTP POST |
| Posting prep (posting_prep, eyemed_posting_prep, eyemed_posting_prep_all) | Daily workflow: prepare files for manual posting team | High | GCS, GDrive, subprocess |
| Storage browsing (list_s3_remits, list_gcs_aiout, gcs_inventory) | Debugging: "did the PDF arrive?", "is the AIOUT there?" | Med | S3, GCS |
| Pipeline status (check_pipeline_status, pipeline_stage_view) | Quick health check for specific location/date | Med | S3, GCS, GDrive |
| Deploy version check | Basic operational awareness | Low | HTTP GET only |
| Prefect flow status (check_prefect_flow_status, get_prefect_logs) | Diagnosing why things are not processing | Med | SSH to production |

### Differentiators for MCP Parity

Features that make SuperBot MORE valuable than local Claude Code for ops.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Autopost tools (vsp_autopost, eyemed_autopost) | Post payments without opening laptop; dry_run=True default | High | Revolution EMR subprocess; test dry_run thoroughly first |
| Benefits fetch (3 tools) | Trigger long-running Prefect jobs from Slack, wait up to 10 min | High | Polls Prefect API; long timeouts may need special handling |
| Azure mirror audit + trigger | Monitor 24-location CrystalPM sync from Slack | High | SSH + direct Cloud SQL access |
| IVT ingestion audit | Cross-system health (Prefect + prod-ivt DB) from Slack | High | SSH + DB |
| Provider revenue analytics | Business intelligence query from Slack | Med | DB only |
| EyeMed status range | Multi-day processing status grid | High | GCS + GDrive + DB |
| OCEA health check | Production monitoring from Slack | Med | DB |
| PDF ingestion (ingest_pdf) | Handle manual PDFs when crawlers fail | Med | Production API |

### Anti-Features for MCP Parity

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Custom wrappers around MCP tools | MCP tools already have clean interfaces; wrapping adds maintenance burden | Wire the MCP server directly as stdio subprocess -- all tools auto-available |
| Credential management UI | Small team, static credentials; over-engineering | Store credentials as env vars / config files on VM |
| Tool-level access control | Only 2-3 trusted users; channel-based visibility sufficient | Rely on existing Slack access control from v1.0 |
| Re-implementing tool logic | Tools are well-structured; they delegate to production API or run subprocesses | Use existing MCP server as-is |
| Approval gates on mutating tools | PROJECT.md explicitly scopes this out; full autonomy by design | Trust dry_run defaults + team visibility in channel |

---

## Credential Dependency Map (v1.2)

Every tool module needs specific credentials available in the VM environment.

| Credential | Tools That Need It | How Stored in mic_transformer | Priority |
|------------|-------------------|-------------------------------|----------|
| GCS service account | Status, reduction, storage, posting, gdrive, crawler | `config/gcs_utils_config.yml` (embedded JSON key) | CRITICAL |
| AWS S3 access | Status, storage (list_s3_remits), crawler | AWS env vars or `~/.aws/credentials` | CRITICAL |
| Google Drive service account | Status, posting_prep, gdrive_audit, crawler | Service account via `get_drive_service()` | CRITICAL |
| Production API URL | Extraction, reduction, ingestion, deploy | `MIC_TRANSFORMER_API_URL` env var (default: hardcoded) | CRITICAL |
| Prefect API auth | Benefits fetch, check_prefect_flow_status | Hardcoded `shen:tofu` basic auth at 136.111.85.127:4200 | HIGH |
| SSH to production | Prefect flow status, azure_mirror, ivt_ingestion | SSH key for `ansible@136.111.85.127` | HIGH |
| PostgreSQL (IrisMedAppDB) | pipeline_audit, analytics, crawler_audit, posting_prep | `config/db_config.yml` or env vars | HIGH |
| PostgreSQL (crystalpm-mirror) | azure_mirror_audit | Hardcoded: `cpmm_dataloader@34.136.128.245` | MEDIUM |
| PostgreSQL (prod-ivt) | ivt_ingestion_audit | Hardcoded: `ivt_app_user@34.136.128.245` | MEDIUM |
| Revolution EMR | vsp_autopost, eyemed_autopost | Credentials in mic_transformer config | MEDIUM |
| Insurance portals | remit_crawler | Portal credentials in config files + Chrome/Chromium | LOW (defer) |

---

## Read vs Write Classification Summary

| Category | Count | Risk Level | Tools |
|----------|-------|------------|-------|
| **READ-ONLY** | ~20 | None | All status/audit, list_*, deploy_version, list_crawler_locations, provider_revenue, gcs_inventory |
| **WRITE via HTTP API** | ~7 | Low (production API validates) | vsp_extract, eyemed_extract, requeue_missing_pages, reduce_aiout, reduce_all_vsp, ingest_pdf |
| **WRITE via Prefect trigger** | ~5 | Med (triggers production jobs) | vision/eyemed/medical_benefits_fetch, azure_mirror_trigger, (benefits poll for 10 min) |
| **WRITE via subprocess** | ~5 | High (local execution) | vsp/eyemed_autopost, posting_prep, remit_crawler, clear_pipeline |
| **WRITE via SSH** | ~2 | Med (remote execution) | azure_mirror_trigger, check_prefect_flow_status |

---

## Integration Pattern Analysis

| Pattern | Tools Using It | What VM Needs | Complexity |
|---------|---------------|---------------|------------|
| **HTTP to production API** | extraction, reduction, ingestion, deploy | Network route to 136.111.85.127:8080 | Low |
| **Direct GCS access** | status, storage, reduction pre-check, posting, gdrive | GCS service account JSON in `config/` | Med |
| **Direct S3 access** | status, storage | AWS credentials (`~/.aws/credentials` or env vars) | Med |
| **SSH to production** | prefect flow status, azure mirror, ivt ingestion | SSH key for `ansible@136.111.85.127` | Med |
| **Direct DB access** | analytics, pipeline_audit, eyemed_crawler_audit | DB connection config in `config/` | Med |
| **Subprocess execution** | posting (autoposter), crawler, clear_pipeline, ocea_health_check | Full mic_transformer repo + activated venv | High |
| **GDrive API** | gdrive_audit, check_pipeline_status, posting_prep | GDrive service account credentials | Med |

---

## Pipeline Workflow Dependencies

```
-- Core Pipeline Workflow (sequential dependency chain) --
remit_crawler -> vsp/eyemed_extract -> reduce_aiout -> posting_prep -> vsp/eyemed_autopost
      |                    |                 |               |                  |
      v                    v                 v               v                  v
  S3 + GCS           Prod API            Prod API      GCS + GDrive     Revolution EMR
  (portal creds)     (Celery workers)    (Celery)      (subprocess)      (subprocess)

-- Status tools observe every stage --
vsp_status / eyemed_status -> reads from: S3, GCS, GDrive, DB (aggregates all stages)

-- Independent operational tools (no pipeline dependency) --
check_prefect_flow_status  -- SSH to production, journalctl parsing
azure_mirror_audit/trigger -- SSH + DB (separate CrystalPM system)
ivt_ingestion_audit        -- SSH + DB (separate IVT system)
vision_benefits_fetch      -- Prefect API (separate benefits system)
provider_revenue           -- DB query only
deploy_version             -- HTTP GET only
ocea_health_check          -- DB query only
```

---

## MVP Recommendation for v1.2

### Phase 1: Wire MCP server + read-only tools
1. All status/audit tools -- Nicole's most frequent ask is "what's the status?"
2. Storage browsing tools -- "Did the PDF arrive? Is the AIOUT there?"
3. Deploy version check -- simple validation that MCP server works
4. Pipeline status tools -- single-location diagnostics

**Needs:** GCS, S3, GDrive, DB credentials configured on VM. MCP server running as stdio subprocess.

### Phase 2: API-triggered mutating tools
5. Extraction triggers (vsp/eyemed_extract, requeue_missing_pages) -- daily workflow
6. Reduction triggers (reduce_aiout, reduce_all_vsp) -- daily workflow
7. PDF ingestion (ingest_pdf) -- fallback for crawler failures

**Needs:** Network access to production API at 136.111.85.127:8080

### Phase 3: Prefect + SSH tools
8. Prefect flow status (check_prefect_flow_status, get_prefect_logs)
9. Benefits fetch (vision/eyemed/medical_benefits_fetch)
10. Azure mirror tools
11. IVT ingestion audit

**Needs:** SSH key for ansible@production, Prefect API auth

### Phase 4: Subprocess-based mutating tools
12. Posting prep (posting_prep, eyemed_posting_prep, eyemed_posting_prep_all)
13. Autopost (vsp/eyemed_autopost) -- test dry_run thoroughly before live use
14. clear_pipeline -- test dry_run thoroughly

**Needs:** Full mic_transformer venv with all dependencies, Revolution EMR credentials

### Defer
- **remit_crawler**: Needs Chrome/Chromium browser on VM + insurance portal credentials. Consider whether headless mode is viable on the GCP VM.
- Crawler can be triggered manually on production server via SSH if needed as interim.

---

## Feature Dependencies (v1.0/v1.1 Baseline)

```
[Slack @mention listener]
    +--requires--> [Allowlist user check]
                       +--requires--> [Claude Code session launch]
                                          +--requires--> [VM shell + Claude Code CLI installed]

[Claude Code session launch]
    +--requires--> [mic_transformer repo cloned on VM]
    +--requires--> [CLAUDE.md + project memory configured]

[Progress updates to Slack]
    +--requires--> [Claude Code session launch]
    +--requires--> [Slack bot write permissions in channel]

[PR creation]
    +--requires--> [Git operations working]
    +--requires--> [GitLab credentials on VM]
    +--requires--> [Claude Code session launch]

[Script execution (Prefect flows)]
    +--requires--> [VM Python environment + mic_transformer deps installed]
    +--requires--> [Claude Code session launch]

[Isolated task workspaces]
    +--requires--> [Task queue]
    +--requires--> [Git worktree management]
    +--enhances--> [Claude Code session launch]

[Task queue + /status command]
    +--requires--> [SQLite or equivalent on VM]
    +--enhances--> [Isolated task workspaces]

[Automatic test running]
    +--requires--> [Script execution working]
    +--enhances--> [PR creation]

[Daily digest]
    +--requires--> [Task history stored]
    +--requires--> [Slack bot write permissions]

[Deployment from Slack]
    +--requires--> [Script execution working]
    +--requires--> [Deploy scripts in mic_transformer]
```

---

## Competitor Feature Analysis

| Feature | Claude Code in Slack (official) | Kilo for Slack | GitHub Copilot in Slack | Our Approach |
|---------|--------------------------------|----------------|-------------------------|--------------|
| @mention trigger | Yes, channel only | Yes | Yes (@GitHub) | Yes, channel only per PROJECT.md |
| Thread context reading | Yes | Yes, full thread | Yes, full thread | Yes |
| PR creation | Yes (one PR per session) | Yes | Yes | Yes |
| Progress updates | Yes, status updates in thread | Not described | Reply when PR ready | Yes |
| Multi-repo support | Yes (auto-selects) | Yes | Yes | No -- mic_transformer only |
| Q&A about codebase | Yes | Yes | Yes | Yes (natural via Claude Code) |
| Script execution | Yes (via Claude Code CLI) | Not described | Limited | Yes (core use case) |
| User access control | Workspace admin + channel invite | Not described | GitHub Copilot plan | Named allowlist |
| Persistent memory | Yes (CLAUDE.md) | Not described | Not described | Yes (CLAUDE.md + git) |
| Full autonomy (no approval gates) | No -- web UI oversight | No | No -- opens draft PR for review | Yes -- by design |
| Domain-specific MCP tools | No | No | No | Yes -- 35+ mic-transformer tools |

**Key insight:** No commercial product ships with 35+ domain-specific operational tools. SuperBot's MCP integration makes it an operational platform, not just a coding agent.

---

## Sources

- Direct source code analysis: `mic_transformer/.claude/mcp/mic-transformer/` (all 13 tool modules, server.py, common.py) -- HIGH confidence
- Claude Code in Slack official docs: https://code.claude.com/docs/en/slack -- HIGH confidence
- Kilo for Slack feature page: https://kilo.ai/features/slack -- MEDIUM confidence
- GitHub Copilot coding agent in Slack: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-slack -- HIGH confidence
- Anthropic long-running agent harnesses: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents -- HIGH confidence

---
*Feature research for: Slack-integrated autonomous coding agent (Super Bot)*
*Last updated: 2026-03-23 (v1.2 MCP Parity milestone)*
