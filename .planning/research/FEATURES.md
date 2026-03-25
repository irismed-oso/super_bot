# Feature Landscape

**Domain:** Slack-integrated production ops (deploy, rollback, logs, health, pipeline monitoring)
**Researched:** 2026-03-25 (v1.8 Production Ops milestone)
**Confidence:** HIGH -- derived from direct codebase analysis of existing bot, deploy scripts, and infrastructure

---

## Existing Infrastructure (What v1.8 Builds On)

Before defining new features, these are the existing capabilities that v1.8 extends:

| Existing Feature | Module | Relevance to v1.8 |
|-----------------|--------|-------------------|
| Fast-path command system | `bot/fast_commands.py` | Deploy, health, pipeline commands will be fast-path |
| Background task monitor | `bot/background_monitor.py` | Deploy progress tracking reuses this pattern |
| Prefect API client | `bot/prefect_api.py` | Pipeline status queries |
| Bot status fast-path | `_handle_bot_status()` | Health dashboard extends this |
| Deploy script (local) | `scripts/deploy.sh` | Template for Slack-triggered deploy |
| Restart script | `scripts/restart_superbot.sh` | Already does SSH + systemctl |
| Task state tracking | `bot/task_state.py` | Uptime, recent tasks for health dashboard |
| Queue manager | `bot/queue_manager.py` | Current task, queue depth for health |
| MCP `deploy_version` tool | mic-transformer MCP | Already checks production API version |

---

## Table Stakes

Features the team will expect from a "production ops from Slack" milestone. Missing any of these and the milestone feels incomplete.

| Feature | Why Expected | Complexity | Dependencies | Notes |
|---------|--------------|------------|--------------|-------|
| **Deploy super_bot from Slack** | "deploy" is literally the milestone name; self-deploy is the first test | Medium | SSH to VM, systemctl access | Adapts existing `scripts/deploy.sh` logic into a fast-path handler. Git pull + restart + health check. |
| **Deploy mic_transformer from Slack** | Primary managed repo; most frequent deploy target | Medium | SSH to VM, production API health endpoint | Similar to super_bot deploy but targets mic_transformer dir. Must handle deps install. |
| **Deploy status (what's running)** | Before deploying, "what version is running?" is always the first question | Low | `git rev-parse HEAD` on VM, systemctl status | Show current commit hash, branch, last deploy time, changes since last deploy. |
| **Git-based rollback** | Every deploy system needs an undo; "that broke things, go back" | Medium | Git history on VM, deploy mechanism | `git checkout <previous-commit>` + restart. Must track what was deployed. |
| **Journald log tail** | "What's in the logs?" is the universal first debug step | Low | `journalctl -u superbot` via SSH or local | Tail last N lines with optional grep filter. Output truncation for Slack's 4000-char limit. |
| **Bot health summary** | "Is the bot healthy?" needs more than current idle/busy status | Low | Extends existing `_handle_bot_status()` | Uptime, error count, last restart, memory, queue depth, recent task success rate. |
| **Pipeline status (fast-path)** | "How are the crawls doing?" is asked daily | Medium | Prefect API queries | Summary of recent Prefect flow runs: completed, failed, running counts. |

## Differentiators

Features that go beyond basic expectations and make the ops experience genuinely better than SSH-ing into the VM manually.

| Feature | Value Proposition | Complexity | Dependencies | Notes |
|---------|-------------------|------------|--------------|-------|
| **Deploy with automatic health verification** | Deploy + wait + verify + report pass/fail in one command, no manual checking | Medium | Health check endpoint or journald error scan | Existing `deploy.sh` already does this; wrap it for Slack with structured output. |
| **Rollback with reason tracking** | "Why did we roll back?" captured in Slack thread for team awareness | Low | Deploy history | Append reason to rollback message. Thread becomes audit trail. |
| **Prefect flow log access** | "Show me the logs for that failed crawl" without opening Prefect UI | Medium | Prefect API `get_prefect_logs` MCP tool | Already exists as MCP tool; expose as fast-path for common queries. |
| **Application log access** | Tail app-level logs (Flask, Celery worker output) in addition to journald | Medium | Log file paths on VM, SSH access | mic_transformer may log to files or just stdout captured by systemd. |
| **Deploy diff preview** | "What would be deployed?" shows commits between current and latest | Low | `git log` between HEAD and origin/main on VM | Prevents surprise deploys. |
| **Multi-repo deploy from one command** | "deploy mic_transformer" vs "deploy super_bot" -- repo is a parameter | Low | Repo config map with paths, services, health checks | Unified interface instead of separate scripts per repo. |
| **Pipeline status with date filter** | "pipeline status for 03.20" shows that day's crawl/extraction/posting results | Medium | Existing MCP status tools | Leverages existing `vsp_status`/`eyemed_status` MCP tools. |
| **Error rate tracking** | "How many errors in the last hour?" from journald or app logs | Medium | Log parsing, counters | Useful for post-deploy monitoring. |

## Anti-Features

Features that seem useful but should be explicitly avoided.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Approval gates for deploy** | PROJECT.md explicitly rules out approval gates; full autonomy is a design decision for this 2-person team. Adding "are you sure?" dialogs defeats the speed advantage. | Trust the team. Everything happens in a visible channel. Use rollback if something goes wrong. |
| **Blue-green or canary deploys** | Over-engineering for a single-VM, internal-only tool. No traffic splitting infrastructure exists. | Simple restart deploy. If it breaks, rollback immediately. Downtime is measured in seconds. |
| **Deploy queue/scheduling** | "Deploy at 2am" adds scheduling complexity for zero value -- the team deploys when they want to. | Deploy immediately when asked. |
| **Log streaming (continuous)** | Continuous log streaming to Slack will hit rate limits (1 msg/sec) and flood the channel. | Tail last N lines on demand. Post a snapshot, not a stream. |
| **Alerting/pagerduty integration** | The bot itself IS the alerting mechanism. Adding PagerDuty for a 2-person team adds noise without value. | Daily digest already covers health. Bot status command for on-demand checks. |
| **Deploy to all 4 repos at once** | oso-fe-gsnap and oso-desktop have different deploy targets (not the superbot VM). Deploying them requires different infrastructure. | Support mic_transformer and super_bot first (both on the same VM). Add others only when actual deploy paths exist. |
| **Web-based log viewer** | Slack is the only UI. Building a log viewer is scope creep. | Journald tail via Slack is sufficient. Link to GCP Console for deep dives. |
| **Persistent deploy history database** | SQLite deploy tracking adds maintenance burden for minimal value when git log IS the deploy history. | Use git reflog or a simple JSON file for last-N deploys. Git log shows what was deployed when. |

---

## Feature Details

### Deploy from Slack

**Expected behavior:**
```
User: "deploy super_bot"
Bot:  "Deploying super_bot (branch: main)..."
      "Step 1/4: Pulling latest code... done"
      "Step 2/4: Installing dependencies... done"
      "Step 3/4: Restarting service... done"
      "Step 4/4: Health check... PASS"
      "Deploy complete. Running commit abc1234 (main)"
```

**What it does under the hood:**
1. SSH to VM (or run locally for super_bot since bot IS on the VM)
2. `git pull origin <branch>`
3. `pip install -r requirements.txt` (unless `--skip-deps`)
4. `systemctl restart <service>`
5. Wait 3-5 seconds, check `systemctl is-active`
6. Scan last 20 journald lines for ERROR/Traceback
7. Report pass/fail

**For super_bot specifically:** The bot is deploying itself. After restart, the current process dies. The NEW process picks up the Slack connection via Socket Mode reconnect. The deploy confirmation message must be sent BEFORE restart, or use a fire-and-forget approach where the restarted bot posts "I'm back" on startup.

**Repo config map:**
| Repo | VM Path | Service Name | Health Check |
|------|---------|-------------|-------------|
| super_bot | `/home/bot/super_bot` | `superbot` | systemctl + journald |
| mic_transformer | `/home/bot/mic_transformer` | N/A (API server) | HTTP GET healthcheck |
| irismed-service | TBD | TBD | TBD |
| oso-fe-gsnap | TBD | TBD | TBD |

**Start with super_bot and mic_transformer only** -- the other two repos are on different infrastructure.

### Rollback

**Expected behavior:**
```
User: "rollback super_bot"
Bot:  "Current version: abc1234 (deployed 2h ago)"
      "Rolling back to previous: def5678"
      "Restarting service... done"
      "Health check... PASS"
      "Rolled back to def5678. Previous: abc1234"
```

**Implementation:** `git log --oneline -5` to find previous commits. `git checkout <commit>` (detached HEAD) or `git reset --hard <commit>`. Then restart service. Track last-known-good commit.

**Edge case:** Rolling back super_bot kills the running bot process. Same self-deploy challenge.

### Log Access

**Expected behavior:**
```
User: "logs superbot"         -> last 30 lines of journald
User: "logs superbot errors"  -> last 30 lines filtered for ERROR
User: "logs superbot 100"     -> last 100 lines
User: "prefect logs <run-id>" -> Prefect flow run logs
```

**Output truncation:** Slack messages max at ~4000 chars. For longer output, truncate with "... (showing last 30 of 247 lines). Use `logs superbot 50` for more."

**Log sources:**
| Source | Command | Use Case |
|--------|---------|----------|
| SuperBot journald | `journalctl -u superbot -n 30 --no-pager` | Bot crashes, startup errors |
| mic_transformer API | `journalctl -u mic-transformer-api -n 30` (if systemd) or log file tail | API errors |
| Prefect flow logs | Prefect API `get_prefect_logs` | Crawl/extraction failures |
| Application logs | Tail specific log files if they exist | App-level debugging |

### Bot Health Dashboard

**Expected behavior:**
```
User: "health" or "bot health"
Bot:  "SuperBot Health
       Uptime: 4h 23m
       Status: Idle
       Queue: 0 waiting
       Last restart: 2026-03-25 10:15 UTC
       Recent tasks: 12 completed, 1 failed (last 24h)
       Memory: 245 MB RSS
       Disk: 42% used (/home/bot)
       Active monitors: 1 (batch crawl 03.25)"
```

**Extends existing `_handle_bot_status()`** which already shows idle/running/background status. Add:
- Error count from recent tasks
- Memory usage (`psutil` or `/proc/self/status`)
- Disk usage
- Last restart time (from systemd or process start time)
- Recent task success/fail counts

### Pipeline Status

**Expected behavior:**
```
User: "pipeline status"
Bot:  "Pipeline Status (last 24h):
       Crawls: 23 completed, 0 failed
       Extractions: 18 completed, 2 running, 3 pending
       Reductions: 15 completed
       Posting prep: 12 completed

       Failed runs:
       - eyemed-crawler-ECLANT: CRASHED (timeout after 30m)"
```

**Two tiers:**
1. **Fast-path** (new): Quick Prefect API summary of recent flow run states. No agent needed.
2. **Agent deep-dive** (existing): Full investigation using MCP status tools. Already works via agent pipeline.

---

## Feature Dependencies

```
[Deploy from Slack]
    +--requires--> [SSH access to VM (already exists)]
    +--requires--> [Git pull capability]
    +--requires--> [systemctl restart access]
    +--requires--> [Health check mechanism]
    +--enables---> [Rollback]
    +--enables---> [Deploy status]

[Rollback]
    +--requires--> [Deploy from Slack (same mechanism)]
    +--requires--> [Deploy history tracking (git log)]

[Log Access]
    +--requires--> [journalctl access (already exists)]
    +--requires--> [Prefect API (already exists)]
    +--requires--> [Output truncation for Slack]

[Bot Health Dashboard]
    +--extends---> [Existing _handle_bot_status()]
    +--requires--> [task_state module (already exists)]
    +--requires--> [psutil or /proc for memory/disk]

[Pipeline Status (fast-path)]
    +--requires--> [Prefect API (already exists)]
    +--requires--> [Fast-path command infrastructure (already exists)]
```

---

## MVP Recommendation

### Priority 1: Deploy + Rollback (highest value, enables everything else)
1. Deploy super_bot from Slack (self-deploy with restart handling)
2. Deploy mic_transformer from Slack
3. Deploy status (what commit is running)
4. Git-based rollback

**Rationale:** Deployment is the single highest-friction operation today. It requires SSH, manual commands, and waiting. Making it a one-liner in Slack saves minutes per deploy and encourages more frequent, smaller deploys.

### Priority 2: Log Access (most requested debug tool)
5. Journald tail (last N lines, with optional filter)
6. Prefect flow log access via fast-path

**Rationale:** After deploy, "why is it broken?" is the next question. Log access via Slack eliminates the SSH round-trip for the most common debugging workflow.

### Priority 3: Health + Pipeline Status (observability)
7. Enhanced bot health dashboard
8. Pipeline status fast-path summary

**Rationale:** These are incremental improvements to existing bot status. Lower urgency because the team can already ask the bot "are you broken?" and get a useful answer.

### Defer
- **irismed-service and oso-fe-gsnap deploy**: Different infrastructure, unknown deploy paths. Add when those repos' deploy workflows are defined.
- **Application log file tailing**: Only if journald doesn't capture what's needed. Check first.
- **Error rate tracking**: Nice-to-have after core features ship.

---

## Complexity Assessment

| Feature | Complexity | Estimate | Risk |
|---------|------------|----------|------|
| Deploy super_bot | Medium | 1-2 phases | Self-restart is tricky; bot dies mid-deploy |
| Deploy mic_transformer | Medium | 1 phase | Straightforward SSH + restart |
| Deploy status | Low | 0.5 phase | Git commands on VM |
| Rollback | Medium | 1 phase | Same self-restart challenge for super_bot |
| Journald log tail | Low | 0.5 phase | Subprocess + output truncation |
| Prefect log fast-path | Medium | 1 phase | Need flow run ID resolution |
| Bot health dashboard | Low | 0.5 phase | Extends existing handler |
| Pipeline status fast-path | Medium | 1 phase | Prefect API aggregation queries |

**Total estimated effort:** 6-8 phases

---

## Sources

- Direct source code analysis: `bot/fast_commands.py`, `bot/handlers.py`, `bot/prefect_api.py`, `bot/background_monitor.py`, `bot/task_state.py`, `scripts/deploy.sh`, `scripts/restart_superbot.sh` -- HIGH confidence
- `.planning/PROJECT.md` for constraints and design decisions -- HIGH confidence
- Existing deploy patterns from `scripts/deploy.sh` (push, pull, deps, restart, health check) -- HIGH confidence
- systemd/journald behavior from GCP VM setup (already validated in v1.0-v1.7) -- HIGH confidence

---
*Feature research for: v1.8 Production Ops (deploy, rollback, logs, health, pipeline monitoring)*
*Last updated: 2026-03-25*
