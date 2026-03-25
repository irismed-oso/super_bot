# Pitfalls Research

**Domain:** Production ops features (deploy-from-Slack, rollback, log streaming, health monitoring)
**Researched:** 2026-03-25
**Confidence:** HIGH (based on codebase analysis, systemd behavior, Slack API constraints, and SSH subprocess patterns)

## Critical Pitfalls

### Pitfall 1: Self-deploy kills the bot before it can confirm success

**What goes wrong:**
User says "deploy super_bot" from Slack. The bot triggers `systemctl restart superbot`, which sends SIGTERM to the running Python process. The async event loop, Socket Mode connection, and all in-flight Slack API calls die immediately. The user never gets a success or failure message. Worse: if the new code is broken, the bot is dead and cannot report the failure or accept commands.

**Why it happens:**
The bot IS the systemd service being restarted. `systemctl restart` kills the caller. There is no "afterlife" to post results. The existing `deploy.sh` works because it runs from a developer's laptop (external to the VM process), but a Slack-triggered deploy runs inside the process being killed.

**How to avoid:**
1. Post "Deploying now -- I will be back shortly" BEFORE triggering restart.
2. Use `systemd-run --scope` or a detached shell process (`nohup bash -c '...' &`) to run the restart command so it survives the bot process dying.
3. On startup, check for a deploy-state file (e.g., `/home/bot/.superbot_deploy_pending.json` containing `{channel, thread_ts, pre_sha, post_sha}`). If found, post "Deploy complete" or "Deploy failed" to the saved thread, then delete the file.
4. The startup confirmation must handle the failure case: if the bot crashes on startup, the file persists and the user knows to SSH in.

**Warning signs:**
- Testing deploy only for OTHER services (mic_transformer), not self-deploy.
- No post-restart confirmation logic in `bot/app.py` startup path.
- Deploy appears to work in dev because you're running the bot in a terminal (not systemd).

**Phase to address:**
Deploy-from-Slack phase -- this is the foundational design decision. Must be solved architecturally before any deploy code is written.

---

### Pitfall 2: Deploy during active agent session destroys in-progress work

**What goes wrong:**
Nicole is mid-conversation with the bot (agent session running, worktree created, heartbeat active). Han triggers "deploy super_bot." The restart kills the active session. The worktree is left in a dirty state with uncommitted changes. The heartbeat timer fires into a dead Slack client. Nicole gets no result for her in-progress task and no explanation of what happened.

**Why it happens:**
The deploy command does not check `queue_manager.get_state()` to see if a task is running. It fires the restart immediately. The queue serialization prevents concurrent agent sessions but does not prevent a deploy from nuking a running session.

**How to avoid:**
1. Before deploying super_bot, check `get_current_task()`. If a task is running, warn: "A task is in progress. Deploy will kill it. Say 'deploy force' to proceed."
2. For non-super_bot deploys (mic_transformer, irismed-service, oso-fe-gsnap), this is not an issue -- those are separate services on separate VMs.
3. When force-deploying over an active session, call `worktree.stash(thread_ts)` and post a message to the interrupted thread: "Deploy interrupted your session. Changes were stashed in the worktree."
4. After restart, clean up any orphaned heartbeat state.

**Warning signs:**
- Testing deploys only when the bot is idle.
- No thread notification when a session is killed by deploy.
- No pre-deploy check for running tasks in the deploy handler.

**Phase to address:**
Deploy-from-Slack phase -- must include running-task awareness from the start.

---

### Pitfall 3: SSH subprocess hangs and blocks the entire bot

**What goes wrong:**
The bot runs `gcloud compute ssh ... -- "command"` as a subprocess. The SSH connection hangs (network issue, VM unresponsive, gcloud auth expired, or remote command stalls). Because the bot uses asyncio subprocess, a stuck process blocks the queue slot indefinitely. No other tasks can run. The bot appears frozen to all users.

**Why it happens:**
SSH has no inherent timeout. `gcloud compute ssh` can hang during key exchange or if the target VM is in a bad state. The existing `FAST_CMD_TIMEOUT = 30` in `fast_commands.py` applies only to `_run_script` calls for local Python scripts. Deploy/rollback SSH commands run against remote VMs and have no timeout wrapper. Even if deploy runs as a background task, an SSH hang wastes the background slot and leaks a subprocess.

**How to avoid:**
1. Always wrap SSH calls with `asyncio.wait_for(proc.communicate(), timeout=90)`.
2. Pass SSH options via gcloud: `gcloud compute ssh ... -- -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3`.
3. Run deploy/rollback as background tasks (like the existing batch crawl monitor) so they don't block the agent queue.
4. On timeout, explicitly kill the subprocess (`proc.kill()`) and report the failure to Slack.
5. Create a shared `_run_ssh_command(vm, command, timeout=90)` helper that all ops commands use, with timeout and error handling baked in.

**Warning signs:**
- No timeout on any `gcloud compute ssh` call.
- Testing only on a healthy, immediately responsive VM.
- Deploy runs inline in the fast-path handler without background isolation.

**Phase to address:**
Deploy-from-Slack phase -- the SSH helper with timeout must be built before any remote command execution.

---

### Pitfall 4: Rollback to an incompatible commit with no recovery path

**What goes wrong:**
User rolls back to a previous git SHA. That SHA has an incompatible pip dependency, references an env var that was since renamed, or assumes a database column that was migrated. The service crashes on startup after restart. The rolled-back version does not work, the previous version is no longer checked out, and the bot is offline.

**Why it happens:**
`git checkout <sha>` reverts code only. It does not revert pip dependencies, environment variables, systemd unit changes, or external state (database schema, Prefect deployments). The rollback looks clean in git but the runtime environment is incompatible.

**How to avoid:**
1. Before rollback, record the current SHA as "pre-rollback" in a state file. This is the "roll forward" target if rollback fails.
2. Only allow rollback to recent commits (last 10) -- not arbitrary SHAs. Recent commits are most likely to be environment-compatible.
3. After `git checkout` + `pip install` + `systemctl restart`, run the health check. If health check fails, automatically revert to the pre-rollback SHA and restart again.
4. Store a "last known good" SHA that passed the most recent health check. Use this as the ultimate safety net.
5. Re-run `pip install -r requirements.txt` after checkout -- rollback without dep reinstall is a common source of breakage.

**Warning signs:**
- Rollback command has no health check after restart.
- No "undo rollback" mechanism.
- Testing rollback only between trivial code changes.

**Phase to address:**
Rollback phase -- must include health check and automatic roll-forward on failure.

---

### Pitfall 5: Log output floods Slack or is unreadable

**What goes wrong:**
User asks "show me the logs." The bot runs `journalctl -u superbot -n 50`, returning 200+ lines of structlog JSON output. This exceeds Slack's ~4000 character limit. The bot either: (a) truncates, losing the error at the end that the user actually wanted, (b) posts 5-10 chunked messages that flood the thread with unreadable JSON, or (c) the existing `split_long_message(max_chars=3800)` splits mid-JSON-line, producing garbled chunks.

**Why it happens:**
Each structlog log line includes timestamp, logger name, level, and all bound context fields as JSON. A single line can be 200+ characters. 50 lines easily exceeds 4000 characters. The existing formatter handles Slack limits for agent output (which is human-readable text), but raw log output is a different beast -- dense, repetitive, and machine-formatted.

**How to avoid:**
1. Default to small line counts (15-20 lines, not 50).
2. Parse structlog JSON and extract only timestamp + level + event message. Strip context fields unless the user asks for verbose/raw output.
3. Filter by severity: default to WARNING+ with an explicit "all levels" option.
4. For large outputs (>3000 chars), use Slack `files_upload_v2` to post as a downloadable text file instead of inline messages. Files render with scroll and are searchable.
5. Support user-specified filters: "logs superbot errors last 5 min", "logs grep queue_loop".
6. Color-code severity in Slack: bold errors, regular for info.

**Warning signs:**
- Testing log commands with short/quiet log output only.
- No cap on `journalctl -n` lines.
- Not testing with DEBUG-level logging enabled (which is common during troubleshooting -- the exact time you need the log command).

**Phase to address:**
Log access phase -- output formatting and size management must be designed upfront.

---

### Pitfall 6: Fast-path regex collisions with new ops commands

**What goes wrong:**
Adding new fast-path commands (`deploy`, `rollback`, `logs`, `health`, `status`) creates regex collisions with existing patterns. Examples: "deploy status" matches the deploy handler when it should match a status subcommand. "check the logs from the eyemed crawl" matches the eyemed crawl handler. The `is_action_request()` function blocks "deploy super_bot" because "deploy" matches action stems. The order-sensitive `FAST_COMMANDS` list becomes fragile and hard to reason about.

**Why it happens:**
The current fast-path system uses ordered regex matching (first match wins). Existing commands are well-separated: crawl, eyemed status, bot status. Adding deploy/rollback/logs creates overlapping keyword spaces. The `_ACTION_STEMS` list includes stems like "improv", "fix", "chang", "updat", "modif", "implement", "creat" -- and new ops commands may contain action-like words that trigger `is_action_request()`, routing them to the full agent pipeline instead of the fast path.

**How to avoid:**
1. Use specific prefix patterns with anchoring: `^\s*deploy\b`, `^\s*rollback\b`, `^\s*logs?\b`.
2. Check new ops commands BEFORE the `is_action_request()` guard. Ops commands ARE actions but should fast-path, not go to the agent. Add an ops-command pre-check before the action filter.
3. Write a test matrix covering ambiguous inputs: "deploy status", "rollback the eyemed crawl", "show logs for the deploy", "deploy super_bot", plus all existing commands.
4. Consider restructuring: ops commands get their own `try_ops_command()` function checked before `is_action_request()` and before `try_fast_command()`. This separates concerns.

**Warning signs:**
- New commands work individually but break existing ones.
- User says "deploy status" and gets a deploy execution instead of status output.
- `is_action_request()` returns True for "deploy super_bot", causing it to skip fast-path.

**Phase to address:**
The first phase that adds new fast-path commands (likely deploy phase). Must restructure the command matching before adding commands.

---

### Pitfall 7: Health check only verifies `systemctl is-active`, not actual bot functionality

**What goes wrong:**
After deploy or rollback, the health check runs `systemctl is-active superbot` which returns "active." The service is running, but: (a) the bot is stuck in a Python import error loop (systemd restarts it repeatedly, it crashes, restarts -- `is-active` catches it in a brief "active" window), (b) the bot started but Socket Mode connection failed (no Slack connectivity), (c) the bot started but MCP server initialization failed (no tools available). The deploy reports "success" but the bot is functionally broken.

**Why it happens:**
`systemctl is-active` only checks if the process is running. It says nothing about whether the bot successfully connected to Slack, loaded its MCP servers, or can actually process messages. The existing `deploy.sh` also checks for "ERROR" or "Traceback" in recent logs, which is slightly better but still misses functional failures that don't produce tracebacks (like a silent Socket Mode disconnect).

**How to avoid:**
1. After restart, wait 5-10 seconds (for Python imports, Socket Mode handshake, MCP init).
2. Check `systemctl is-active` (process is running).
3. Check recent journald logs for the startup success marker (add one if it doesn't exist -- e.g., "SuperBot ready, connected to Slack").
4. Optionally: have the bot post a message to a dedicated health channel on startup. The deploy script can check for this message via Slack API.
5. Check for crash loops: `systemctl show superbot -p NRestarts` -- if NRestarts increased, the service is crash-looping.

**Warning signs:**
- Health check is a single `is-active` call with no log inspection.
- No startup success marker in the bot's log output.
- Sleep time before health check is too short (2-3 seconds) for a Python bot with MCP servers.

**Phase to address:**
Deploy-from-Slack phase and Health dashboard phase -- the health check logic should be shared.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Shell out to `gcloud compute ssh` for each command | Simple, matches existing deploy.sh scripts | Slow (SSH handshake per command), fragile (gcloud auth state), no connection reuse | MVP -- acceptable for 4 repos with infrequent deploys. Replace if deploy frequency grows. |
| Hardcoding VM names/zones in fast-path handlers | Quick to implement | Cannot deploy to different VMs without code changes | Acceptable for the 4 known IrisMed repos. Use a config dict mapping repo -> VM. |
| Storing deploy state in temp files | No database dependency for simple state | Lost on VM reboot, no deploy history | Acceptable for self-deploy confirmation only. Use the existing SQLite DB for deploy history. |
| Inline log output in Slack messages | No extra API calls, simple implementation | Unusable for large outputs, floods threads | Never for raw logs over 20 lines. Always use file upload for bulk output. |
| No concurrent deploy protection | Simpler command handling | Two users trigger deploy simultaneously, causing race conditions | Never acceptable -- add a simple lock flag. |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| gcloud compute ssh (from bot process) | Assuming the `bot` system user has the same gcloud auth state as the developer. The bot runs as `bot` user under systemd -- it has no interactive gcloud login. | Use OS Login or metadata-based SSH keys for the bot user. Or configure a service account with `gcloud auth activate-service-account` during VM setup. Verify SSH works as the `bot` user. |
| journalctl via SSH | Using `--since "2024-01-01"` without timezone -- journalctl interprets this in the VM's local timezone which may differ from what the user expects. | Always use UTC: `--since "2026-03-25 10:00:00 UTC"` or relative: `--since "5 minutes ago"`. |
| Prefect Cloud API for pipeline status | Querying all flow runs without date filter -- returns thousands of results, slow and paginated. | Always include `flow_runs/filter` with `after` date parameter. Cache deployment IDs (they rarely change). Add retry with backoff for 429 responses. |
| Slack files_upload_v2 | Using the deprecated `files.upload` endpoint (deprecated since 2024). | Use `files_upload_v2` with `channel_id` parameter. Note: this is a different method signature from the old one. |
| systemctl restart via SSH | Running `systemctl restart` without `sudo` -- the bot user may not have passwordless sudo for systemctl. | Verify sudoers config: `bot ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart superbot` (and similar for other services). Test this from an SSH session as the bot user. |
| Git operations on remote VM | Running `git pull` when there are uncommitted changes on the remote. | Always check `git status --porcelain` first. If dirty, abort and report to the user. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| SSH per command | Deploy takes 30+ seconds because each step (push, pull, install, restart, health) is a separate SSH session with handshake overhead | Batch commands into a single SSH session: `gcloud compute ssh ... -- "cmd1 && cmd2 && cmd3"` | Always -- each SSH handshake is 2-5 seconds |
| Full git log for deploy status | `git log --oneline` on a large repo takes seconds over SSH, and the output can be enormous | Use `--max-count=10` and `git log <last-deploy-sha>..HEAD` to show only changes since last deploy | Repos with 100+ commits since last deploy |
| Prefect API polling in tight loop | Pipeline status command hammers Prefect Cloud API with requests, hits rate limits | Cache pipeline status for 30-60 seconds. Don't poll -- query on demand when user asks. | More than 1 status request per minute |
| journalctl without `--lines` cap | `journalctl -u superbot` dumps entire journal history, SSH transfer is slow and output overflows Slack | Always specify `-n 20` or `--since "10 minutes ago"`. Never run uncapped journalctl. | Always -- journals can be gigabytes |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Posting full log output containing secrets to Slack | journald captures all stdout/stderr including environment dumps from crash tracebacks. API keys, database URLs, tokens appear in error logs. | Scrub log output before posting: regex-match known secret patterns (long base64 strings, URLs with passwords, `KEY=...` patterns). At minimum, truncate any line longer than 200 chars. |
| Deploy command with no access control beyond general bot access | Any authorized bot user can deploy any repo, including production services handling patient data. | For v1.8 with 2-3 trusted users, this is acceptable. Document the risk. If team grows, add a separate `DEPLOY_ALLOWED_USERS` list. |
| Rollback exposes git diff with secrets in Slack | `git log --diff` output could contain previously committed and then rotated secrets. | Never include full diffs in Slack output. Show only commit messages and changed file names, never file contents. |
| SSH credentials on the bot VM have broad access | If the bot can SSH to other VMs for deployment, compromise of the bot means access to all target VMs. | Use scoped SSH keys or service accounts per target VM. For v1.8, document as accepted risk. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Deploy takes 60s with no progress | User thinks bot is broken, triggers another deploy, causing a race | Post step-by-step progress by editing a single Slack message: "Pushing... -> Pulling on VM... -> Installing deps... -> Restarting... -> Health check..." exactly like the heartbeat pattern |
| Raw structlog JSON in log output | User cannot parse machine-formatted JSON lines. The useful information (error message) is buried in context fields. | Parse logs to extract: `{timestamp} [{level}] {event}`. Strip JSON context. Bold errors. Group repeated messages. |
| "Deploy succeeded" with no version info | User does not know what was deployed, cannot verify the right code is running. | Always include: branch name, short SHA, commit message, and count of changes since previous deploy. |
| "Rolled back to abc1234" with no context | Bare SHA is meaningless to the user. | Include: "Rolled back to abc1234 -- 'fix vsp parser timeout' by Han, 2h ago (3 commits back)" |
| Pipeline status is a wall of text | 23 locations x multiple fields = unreadable in Slack | Group by status (failed first, then running, then completed). Show counts per group. Expand only failures. Use the summary/detail pattern already established: fast-path shows summary, agent digs into specifics. |
| Health dashboard shows too much or too little | Either a single "OK" line (useless) or a page of metrics (overwhelming) | Show: uptime, last restart time, current task (if any), error count in last hour, MCP server status, queue depth. One compact message. |

## "Looks Done But Isn't" Checklist

- [ ] **Self-deploy:** Missing post-restart confirmation -- verify the bot posts "I'm back, deploy succeeded" to the deploy thread after restart
- [ ] **Self-deploy:** Missing failure recovery -- verify that if new code crashes on startup, the deploy-state file persists and user can diagnose via SSH
- [ ] **Rollback:** Missing health check after restart -- verify rollback includes health check AND auto-roll-forward on failure
- [ ] **Rollback:** Missing `pip install` after checkout -- verify dependencies are reinstalled, not just code reverted
- [ ] **Log access:** Missing size cap -- verify log output never exceeds Slack 4000 char limit without file upload fallback
- [ ] **Log access:** Missing secret scrubbing -- verify no API keys or tokens appear in Slack-posted log output
- [ ] **Deploy status:** Missing last-deploy SHA persistence -- verify deploy records the deployed SHA somewhere that survives restart (file or DB)
- [ ] **Pipeline status:** Missing pagination for Prefect API -- verify status query works when >200 flow runs exist
- [ ] **Fast-path:** Missing `is_action_request()` bypass for ops commands -- verify "deploy super_bot" routes to deploy handler, not to agent pipeline
- [ ] **Health check:** Only checking `systemctl is-active` -- verify health check also confirms Slack connectivity (startup marker in logs or Slack message)
- [ ] **SSH timeouts:** Missing on every `gcloud compute ssh` call -- verify timeout wrapper exists and is tested
- [ ] **Concurrent deploy prevention:** Missing lock -- verify two simultaneous "deploy" commands do not race

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Self-deploy breaks bot (bad code) | MEDIUM | SSH to VM: `cd /home/bot/super_bot && git checkout <previous-sha> && sudo systemctl restart superbot`. The existing `restart_superbot.sh` script handles the restart part. |
| Rollback to incompatible commit | LOW | Run another rollback to the "known good" SHA (if stored), or `git checkout main && sudo systemctl restart superbot` |
| Log flood in Slack thread | LOW | Delete flood messages via Slack API. Fix line limit. No lasting damage. |
| SSH hang blocks queue | MEDIUM | Bot appears frozen. Recovery: restart bot via SSH (`restart_superbot.sh`). Add SSH timeouts to prevent recurrence. |
| Regex collision breaks existing commands | LOW | Existing commands fall through to agent pipeline when fast-path fails (the `return None` fallback). Fix regex and deploy. |
| Deploy during active session | MEDIUM | Session is lost. Worktree stash preserves code changes. User must re-trigger task after restart. |
| Two concurrent deploys race | LOW | One wins, one fails. No corruption risk because git operations are atomic. But confusing UX. Add lock. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Self-deploy drops confirmation | Deploy-from-Slack | Bot posts "I'm back" after restart; test with intentionally broken commit to verify failure path |
| Deploy during active session | Deploy-from-Slack | Deploy checks `get_current_task()`; warns if task running |
| SSH hangs block bot | Deploy-from-Slack | All SSH calls use 90s timeout wrapper; test with unreachable VM mock |
| Fast-path regex collisions | Deploy-from-Slack (first new fast-path) | Test matrix: "deploy", "deploy status", "rollback", "logs" plus all existing commands unchanged |
| `is_action_request()` blocks ops | Deploy-from-Slack | "deploy super_bot" and "rollback" are not blocked by action detection |
| Rollback to broken commit | Rollback | Health check after rollback; auto-roll-forward tested with broken commit |
| Log output floods Slack | Log access | No inline message exceeds 3800 chars; large output uses file upload |
| Secret leakage in logs | Log access | Regex scrubber tested against known secret patterns in sample logs |
| Health check too shallow | Health dashboard | Health check confirms Slack connectivity, not just `is-active` |
| Prefect API pagination | Pipeline monitoring | Status query correct when >200 runs exist; rate limit retry works |
| Concurrent deploy race | Deploy-from-Slack | Lock prevents two deploys from running simultaneously |

## Sources

- Codebase analysis: `bot/handlers.py` (event flow, fast-path integration), `bot/queue_manager.py` (serial queue, task state), `bot/fast_commands.py` (regex patterns, `is_action_request()`, `_run_script` timeout), `bot/formatter.py` (`split_long_message` at 3800 chars), `scripts/deploy.sh` (SSH deploy flow, health check), `scripts/restart_superbot.sh` (manual restart pattern)
- Slack API: message size limit ~4000 chars, `files_upload_v2` requirement (deprecated `files.upload` since 2024)
- systemd behavior: SIGTERM on `systemctl restart`, `PrivateTmp`, `NRestarts` property
- gcloud compute ssh: SSH timeout behavior, OS Login vs metadata SSH keys
- Prefect Cloud API: default 200 results per page, rate limiting on filter endpoints

---
*Pitfalls research for: v1.8 Production Ops -- deploy, rollback, log access, health monitoring on SuperBot*
*Researched: 2026-03-25*
