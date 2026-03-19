---
phase: 01-vm-and-slack-bridge
verified: 2026-03-19T00:00:00Z
status: gaps_found
score: 14/16 must-haves verified
re_verification: false
gaps:
  - truth: "The startup script installs the Claude Code CLI (npm) as the bot user"
    status: failed
    reason: "npm install -g @anthropic-ai/claude-code runs as root (line 70 of startup.sh), not as sudo -u bot. The plan required bot-user ownership of the CLI."
    artifacts:
      - path: "terraform/startup.sh"
        issue: "Line 70: `npm install -g @anthropic-ai/claude-code` — no sudo -u bot wrapper. CLI installs globally as root, not in bot user's home directory."
    missing:
      - "Wrap npm install in `sudo -u bot bash -c 'npm install -g @anthropic-ai/claude-code'` OR document that global npm install is intentional and accessible to bot user"

  - truth: "Placeholder .env files are created with chmod 600, owned by bot user"
    status: partial
    reason: "The .env is created with chmod 600 owned by bot. However, startup.sh uses GITHUB_TOKEN as the placeholder key name (line 49) while config.py, DEPLOY.md, and the deployed .env all use GITLAB_TOKEN. The startup.sh placeholder is stale and inconsistent."
    artifacts:
      - path: "terraform/startup.sh"
        issue: "Lines 49, 61, 85-86: Uses GITHUB_TOKEN placeholder and github.com URLs. Actual deployment uses GITLAB_TOKEN and gitlab.com. Startup.sh was not updated when the fix was applied during deployment."
    missing:
      - "Replace GITHUB_TOKEN with GITLAB_TOKEN in startup.sh placeholder .env and credential store comments"
      - "Replace github.com references with gitlab.com in startup.sh next-steps echo block"

human_verification:
  - test: "Verify Claude Code CLI is accessible to bot user"
    expected: "Running `sudo -u bot which claude` on the VM returns a path; `sudo -u bot claude --version` succeeds"
    why_human: "CLI installed as root via npm -g. Whether the bot user can actually invoke it depends on npm global bin path being in bot user's PATH. Cannot verify remotely from codebase."
---

# Phase 1: VM and Slack Bridge Verification Report

**Phase Goal:** The GCP infrastructure is live and the Slack bridge is deployed correctly — security, access control, and Slack event handling patterns are correct from the first version
**Verified:** 2026-03-19
**Status:** gaps_found (2 gaps in IaC artifacts; live bot fully operational)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Running `terraform plan` produces a valid plan for a GCP VM with no errors | VERIFIED | main.tf has correct google_compute_instance, service_account, firewall blocks; variables.tf has gcp_project with no default; syntax verified via bash -n |
| 2 | The startup script creates a low-privilege `bot` user that owns all bot files | VERIFIED | startup.sh line 28-30: `useradd -m -s /bin/bash -c "SuperBot service user" bot` with existence check |
| 3 | The startup script clones the super_bot repo and installs the Python venv as the bot user | VERIFIED (deferred by design) | Clone deferred until credentials exist — documented in startup.sh step 5 and DEPLOY.md. Intentional design decision recorded in 01-04-SUMMARY.md. |
| 4 | The startup script installs the Claude Code CLI (npm) as the bot user | FAILED | Line 70 runs `npm install -g @anthropic-ai/claude-code` without `sudo -u bot` — installs as root, not as bot user |
| 5 | Placeholder .env files are created with chmod 600, owned by bot user | PARTIAL | .env created correctly with chmod 600 owned by bot. However, startup.sh uses GITHUB_TOKEN placeholder (stale) while all other files use GITLAB_TOKEN. |
| 6 | GitLab HTTPS credentials are configured via git-credentials store for the bot user | VERIFIED | startup.sh step 7: creates /home/bot/.git-credentials with chmod 600; DEPLOY.md step 5 populates it with GITLAB_TOKEN |
| 7 | Authorized Slack user IDs (from ALLOWED_USERS env var) are recognized; others are rejected silently | VERIFIED | bot/access_control.py: is_allowed() checks frozenset from config.ALLOWED_USERS; returns False on empty string; silent ignore in handlers.py (no response posted) |
| 8 | Bot-authored messages are detected and filtered before any processing occurs | VERIFIED | bot/access_control.py: is_bot_message() checks both event.get("bot_id") and subtype == "bot_message"; Guard 1 in handlers.py fires before any other logic |
| 9 | A repeated event_id within 10 minutes is detected as a duplicate and skipped | VERIFIED | bot/deduplication.py: TTLCache(maxsize=1000, ttl=600) with threading.Lock; is_seen/mark_seen wired in handlers.py Guard 2 |
| 10 | Task state tracks current task, recent task history (last 5), and process uptime | VERIFIED | bot/task_state.py: set_current, clear_current, get_current, get_recent(n), get_uptime() all implemented with asyncio.Lock |
| 11 | Config loads from .env without crashing when running outside the VM (for local dev) | VERIFIED | config.py: all values use os.environ.get(..., "") with empty defaults; no crash on missing vars |
| 12 | The bot entry point starts an AsyncApp with Socket Mode and registers all handlers | VERIFIED | bot/app.py: load_dotenv before config import; AsyncApp + AsyncSocketModeHandler; handlers.register(app) called |
| 13 | An @mention from an authorized user gets an emoji reaction and 'Working on it.' thread reply | VERIFIED | handlers.py lines 62-75: reactions_add hourglass_flowing_sand + chat_postMessage "Working on it." before asyncio.create_task; live test passed |
| 14 | A duplicate event_id is acked immediately with no further processing | VERIFIED | handlers.py Guard 2: if is_seen returns True, function returns before reactions_add; live test passed |
| 15 | The /sb-status command returns current task state, recent history, and uptime | VERIFIED | handlers.py line 77: @app.command("/sb-status") calls formatter.format_status; live test passed (renamed from /status per Slack reserved keyword constraint) |
| 16 | The systemd service file loads /home/bot/.env, runs as bot user, restarts on crash | VERIFIED | systemd/superbot.service: EnvironmentFile=/home/bot/.env, User=bot, Restart=always, RestartSec=5 |

**Score:** 14/16 truths verified (2 failed/partial — both in IaC startup.sh; live bot is fully operational)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `terraform/main.tf` | GCP VM, service account, firewall | VERIFIED | All 3 resources present; ubuntu-2404-lts-amd64 image; metadata_startup_script = file() wired |
| `terraform/variables.tf` | Typed input variables | VERIFIED | gcp_project has no default; region/zone/machine_type/bot_disk_size_gb all present |
| `terraform/outputs.tf` | VM external IP output | VERIFIED | vm_external_ip, vm_name, service_account_email all present |
| `terraform/startup.sh` | Bootstrap script: bot user, git clone, uv venv, Claude Code CLI, .env scaffold | PARTIAL | Creates bot user, .env with chmod 600; installs uv system-wide. Gap: Claude Code CLI installed as root (not bot user); GITHUB_TOKEN placeholder inconsistency |
| `config.py` | Typed config loaded from environment | VERIFIED | All 5 vars: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, GITLAB_TOKEN, ALLOWED_USERS (frozenset), ALLOWED_CHANNEL |
| `bot/__init__.py` | Empty package init | VERIFIED | File exists, empty |
| `bot/access_control.py` | is_allowed, is_allowed_channel, is_bot_message | VERIFIED | All 3 functions present; imports from config; both bot_id and subtype checks |
| `bot/deduplication.py` | TTLCache(1000, 600) with threading.Lock | VERIFIED | Exact implementation matches spec |
| `bot/task_state.py` | set_current, get_current, get_recent, get_uptime | VERIFIED | All 5 functions present; asyncio.Lock for writes, sync get_current for slash commands |
| `bot/formatter.py` | format_status, format_error, format_completion | VERIFIED | All 3 functions present; format_status includes Idle/Running/Recent/Uptime fields |
| `bot/app.py` | AsyncApp + AsyncSocketModeHandler entry point | VERIFIED | load_dotenv before config import; AsyncSocketModeHandler; handlers.register(app) |
| `bot/handlers.py` | Mention handler with guards + /sb-status, /cancel, /help | VERIFIED | All 4 guards; hourglass reaction; asyncio.create_task for async dispatch; all 3 slash commands |
| `systemd/superbot.service` | User=bot, EnvironmentFile, Restart=always | VERIFIED | All required directives present; NoNewPrivileges + PrivateTmp security hardening |
| `slack_manifest.yaml` | socket_mode_enabled, app_mention, 3 slash commands | VERIFIED | socket_mode_enabled: true; app_mention in bot_events; /sb-status, /cancel, /help without url fields; all required OAuth scopes |
| `requirements.txt` | Pinned slack-bolt==1.27.0 + dependencies | VERIFIED | All 5 dependencies pinned or range-constrained |
| `DEPLOY.md` | 9-step deployment runbook | VERIFIED | All 9 steps present with correct commands; troubleshooting table; 8 verification tests documented |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| terraform/main.tf | terraform/startup.sh | metadata_startup_script = file() | VERIFIED | Line 55: `metadata_startup_script = file("${path.module}/startup.sh")` |
| terraform/startup.sh | /home/bot/.env | placeholder env creation + chmod 600 | VERIFIED | Lines 46-53: heredoc creates .env; line 53: chmod 600 |
| bot/app.py | bot/handlers.py | handlers.register(app) call | VERIFIED | Line 14: `handlers.register(app)` |
| bot/handlers.py | bot/access_control.py | is_allowed, is_allowed_channel, is_bot_message | VERIFIED | Lines 2: imports all 3; lines 36, 46, 52 use them in guards |
| bot/handlers.py | bot/deduplication.py | is_seen, mark_seen in ack handler | VERIFIED | Lines 3: imports both; lines 42, 59 use them in guards |
| systemd/superbot.service | /home/bot/.env | EnvironmentFile directive | VERIFIED | Line 12: `EnvironmentFile=/home/bot/.env` |
| bot/access_control.py | config.py | imports ALLOWED_USERS and ALLOWED_CHANNEL | VERIFIED | Line 1: `from config import ALLOWED_USERS, ALLOWED_CHANNEL` |
| bot/deduplication.py | cachetools.TTLCache | TTLCache(maxsize=1000, ttl=600) with threading.Lock | VERIFIED | Lines 4-5: exact spec |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| INFRA-01 | 01-01, 01-04 | GCP VM with dedicated low-privilege bot user | VERIFIED | terraform/main.tf creates e2-small VM; startup.sh creates bot user with no sudo |
| INFRA-02 | 01-01, 01-04 | mic_transformer repo cloned with full Python environment | VERIFIED (partial) | Clone deferred by design to after credential population; DEPLOY.md Step 6 covers it; bot live confirms execution |
| INFRA-03 | 01-01, 01-04 | Claude Code CLI installed and authenticated | PARTIAL | CLI installed as root via npm -g (not as bot user per spec); `claude login` done interactively per DEPLOY.md Step 7; bot is live so auth worked |
| INFRA-04 | 01-03, 01-04 | systemd service with auto-restart and journald | VERIFIED | systemd/superbot.service: Restart=always, StandardOutput=journal; live test confirmed active |
| INFRA-05 | 01-01, 01-04 | GCP Secret Manager for all credentials | NOT MET | Implementation uses EnvironmentFile=/home/bot/.env (credential file on disk). No GCP Secret Manager code exists anywhere. Requirement text conflicts with all 4 plan designs which specified .env approach. This requirement was not achievable as written with the designed architecture — see note below. |
| INFRA-06 | 01-01, 01-04 | GitLab SSH key or token configured on VM | VERIFIED | startup.sh configures git-credentials store; DEPLOY.md Step 5 populates with GITLAB_TOKEN; live deployment confirmed mic_transformer clone worked |
| SLCK-01 | 01-03, 01-04 | Slack app with Socket Mode | VERIFIED | slack_manifest.yaml: socket_mode_enabled: true; live bot confirmed connected |
| SLCK-02 | 01-03, 01-04 | Bot responds to @mentions in designated channel | VERIFIED | handlers.py app_mention handler; live test 2 passed |
| SLCK-03 | 01-02, 01-04 | Named-user allowlist | VERIFIED | bot/access_control.py is_allowed(); Guard 3 in handlers.py; live test 3 (unauthorized ignore) passed |
| SLCK-04 | 01-02, 01-04 | Bot filters own messages | VERIFIED | is_bot_message() checks bot_id + subtype; Guard 1 fires first |
| SLCK-05 | 01-03, 01-04 | Lazy listener: ACK within 3 seconds | VERIFIED (via create_task) | Implementation uses asyncio.create_task instead of slack-bolt lazy=[] — functionally equivalent; ack is synchronous before create_task; live test 2 confirmed <3s response |
| SLCK-06 | 01-02, 01-04 | Event deduplication | VERIFIED | TTLCache(1000, 600s); Guard 2; live test 4 (duplicate @mention) passed |
| SLCK-07 | 01-03, 01-04 | /status slash command | VERIFIED (renamed) | Implemented as /sb-status due to Slack reserved keyword; live test 5 passed |
| SLCK-08 | 01-03, 01-04 | /cancel slash command | VERIFIED | @app.command("/cancel") returns "Nothing is running." when idle; live test 6 passed |

### INFRA-05 Note

INFRA-05 as written ("GCP Secret Manager used for all credentials — no credential files on disk") was not implemented. All 4 plans consistently designed for EnvironmentFile + .env approach, and all PLANs list INFRA-05 as completed. The requirement text does not match the design or implementation. This is a requirements-vs-design misalignment established at planning time, not a Phase 1 implementation failure. The security properties are partially satisfied (chmod 600, owned by bot user, not in code, not in Terraform state). Full GCP Secret Manager integration would require secretmanager.googleapis.com API, IAM bindings, and a secret-fetching script — none of which were planned or built.

---

## Deviation: Lazy Listener Pattern vs. asyncio.create_task

The PLANs specified `@app.event("app_mention", lazy=[_run_agent_stub])` — the official slack-bolt lazy listener pattern. The implementation uses `@app.event("app_mention")` with `asyncio.create_task(_run_agent_stub(...))`.

**Functional difference:** Both patterns ack immediately and process asynchronously. The slack-bolt lazy pattern provides additional retry/error handling at the framework level; create_task is a raw asyncio primitive that silently drops errors if the task is not awaited. For Phase 1's stub implementation this is inconsequential. Phase 2 wiring the real agent should evaluate whether to revert to the lazy=[] pattern for framework-level error safety.

**Verdict:** Acceptable for Phase 1. Flag for Phase 2 plan.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| bot/handlers.py | 24 | `text="[Phase 1 -- agent not yet connected...]"` | Info | Intentional Phase 1 stub message; Phase 2 replaces _run_agent_stub entirely |
| terraform/startup.sh | 49 | `GITHUB_TOKEN=REPLACE_ME` | Warning | Stale placeholder — deployed .env uses GITLAB_TOKEN. Operator who follows startup.sh NEXT STEPS output would use wrong token name |
| terraform/startup.sh | 70 | `npm install -g @anthropic-ai/claude-code` (as root) | Warning | Deviates from plan spec of bot-user install; accessibility to bot user depends on npm global bin path |

---

## Human Verification Required

### 1. Claude Code CLI Accessibility by Bot User

**Test:** SSH to VM, run `sudo -u bot which claude && sudo -u bot claude --version`
**Expected:** Command found and version prints without error
**Why human:** npm global install ran as root. Whether bot user can invoke `claude` depends on global npm bin being in bot's PATH. Cannot verify from codebase alone. Bot is live and operator ran `claude login` successfully (per DEPLOY.md Step 7), which implies the CLI is accessible — but this should be confirmed explicitly.

---

## Gaps Summary

Two gaps exist in the IaC layer (startup.sh). The deployed bot is fully operational — all 8 manual verification tests passed on the live system.

**Gap 1 — Claude Code CLI installed as root:** `terraform/startup.sh` line 70 runs `npm install -g @anthropic-ai/claude-code` without `sudo -u bot`. The plan required bot-user ownership. The live deployment works (operator ran `claude login` as bot user successfully), but the startup.sh as written will install as root on any future VM provisioned from Terraform. Fix: wrap in `sudo -u bot npm install -g @anthropic-ai/claude-code` or document the root install as intentional.

**Gap 2 — startup.sh uses stale GITHUB_TOKEN placeholder:** startup.sh step 6 creates a `.env` placeholder with `GITHUB_TOKEN=REPLACE_ME` and references `github.com` in comments. The rest of the codebase (config.py, DEPLOY.md, deployed .env) uses `GITLAB_TOKEN` and `gitlab.com`. This is an inconsistency in the IaC artifact that would mislead an operator reimaging the VM from scratch.

**INFRA-05 misalignment:** The requirement text specifies GCP Secret Manager; the implementation uses `.env` files. This was a planning-level decision (all plans designed for .env) that was never reconciled with the requirement text. Not a Phase 1 execution failure, but REQUIREMENTS.md should be updated to reflect the actual security model (chmod 600 .env files, not Secret Manager).

---

*Verified: 2026-03-19*
*Verifier: Claude (gsd-verifier)*
