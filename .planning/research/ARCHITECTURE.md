# Architecture Patterns

**Domain:** Production ops features for an existing Slack bot (deploy, rollback, logs, health monitoring)
**Researched:** 2026-03-25

## Current Architecture Summary

The bot follows a clean layered pattern:

```
Slack Events (Socket Mode)
  -> handlers.py (guards, dedup, access control)
    -> fast_commands.py (regex match -> instant response)
    -> queue_manager.py (FIFO queue -> serialized agent execution)
      -> agent.py (Claude Agent SDK with MCP servers)
```

Supporting infrastructure:
- `background_monitor.py` -- asyncio tasks that poll Prefect and post Slack updates
- `prefect_api.py` -- async httpx client for Prefect Cloud API
- `task_state.py` -- in-memory current/recent task tracking
- `heartbeat.py` -- periodic progress message edits during agent sessions
- `git_activity.py` -- post-session commit/PR capture for changelog
- `scripts/deploy.sh` -- local-to-VM deploy via gcloud SSH (push, pull, deps, restart, health check)

Key architectural facts:
- All 4 IrisMed repos are cloned on the VM at `/home/bot/{repo}`
- The bot runs as systemd service `superbot` on GCP VM `superbot-vm` (us-west1-a)
- SSH access via `gcloud compute ssh bot@superbot-vm --zone=us-west1-a`
- Bot process runs as user `bot` with sudo access for systemctl
- Prefect API at `http://136.111.85.127:4200/api` with basic auth

## Recommended Architecture for v1.8

### Design Principle: Fast-Path for All Ops Commands

Every new feature (deploy, rollback, logs, health, pipeline status) should be a **fast-path command** in `fast_commands.py`. These are operational queries/actions that have deterministic behavior -- they do NOT need Claude's reasoning. The agent pipeline is reserved for ambiguous, code-change, or investigative tasks.

Exception: "pipeline status" gets a fast-path summary AND an agent-fallback for deep investigation (already the established pattern -- fast-path tries first, falls through to agent on failure or no match).

### Component Boundaries

| Component | Responsibility | New/Modified | Communicates With |
|-----------|---------------|-------------|-------------------|
| `bot/fast_commands.py` | Regex routing for deploy, rollback, logs, health, pipeline | **Modified** -- add new command entries |
| `bot/deploy_ops.py` | Execute deploy/rollback via subprocess (local on VM) | **New** | fast_commands, config |
| `bot/log_reader.py` | Read journald, Prefect, and app logs | **New** | fast_commands, prefect_api, config |
| `bot/health_ops.py` | Bot health dashboard: uptime, errors, queue, memory | **New** | fast_commands, task_state, queue_manager |
| `bot/pipeline_ops.py` | Pipeline status summary (Prefect flow runs) | **New** | fast_commands, prefect_api |
| `bot/prefect_api.py` | Add flow run listing/filtering and log endpoints | **Modified** -- add `list_recent_flow_runs()`, `get_flow_run_logs()` |
| `config.py` | Add deploy config (repo paths, service names, SSH targets) | **Modified** |

### New Module Details

#### 1. `bot/deploy_ops.py` -- Deploy and Rollback Engine

Handles deploy-from-Slack for all 4 IrisMed repos plus super_bot itself.

```python
# Core operations:
async def deploy_repo(repo_name: str, branch: str | None = None) -> str:
    """Pull latest, install deps, restart service, health check."""

async def rollback_repo(repo_name: str, ref: str = "HEAD~1") -> str:
    """Git reset to ref, reinstall deps, restart service."""

async def get_deploy_status(repo_name: str) -> str:
    """Current commit, branch, last deploy time, changes since."""
```

**Key design decisions:**

- **Run commands locally on VM, not via gcloud SSH.** The bot already runs on the VM. For deploying *itself* (super_bot), it runs git pull + deps locally, then triggers `sudo systemctl restart superbot` (which restarts the bot process -- the command completes before the restart kills it, so the Slack response gets posted first). For the other 4 repos, the bot is already on the same VM and can run commands directly in their directories.

- **No gcloud SSH needed.** The existing `scripts/deploy.sh` uses gcloud SSH because it runs from a developer's laptop. The bot runs ON the VM. Direct subprocess calls to git/pip/systemctl are simpler and faster.

- **Repo registry in config.** A dict mapping repo names to their paths, service names (if any), and venv paths. Not all repos have systemd services -- some are just codebases that get pulled.

```python
# config.py addition
DEPLOY_REPOS: dict[str, dict] = {
    "super_bot": {
        "path": "/home/bot/super_bot",
        "service": "superbot",
        "venv": "/home/bot/super_bot/.venv",
        "branch": "main",
    },
    "mic_transformer": {
        "path": "/home/bot/mic_transformer",
        "service": None,  # no systemd service, just a codebase
        "venv": "/home/bot/mic_transformer/.venv",
        "branch": "develop",
    },
    "irismed-service": {
        "path": "/home/bot/irismed-service",
        "service": None,
        "venv": "/home/bot/irismed-service/.venv",
        "branch": "develop",
    },
    "oso-fe-gsnap": {
        "path": "/home/bot/oso-fe-gsnap",
        "service": None,
        "venv": "/home/bot/oso-fe-gsnap/.venv",
        "branch": "develop",
    },
    "oso-desktop": {
        "path": "/home/bot/oso-desktop",
        "service": None,
        "venv": None,  # may not have venv on VM
        "branch": "develop",
    },
}
```

- **Self-deploy is special.** When deploying super_bot, the bot must post the Slack response BEFORE restarting itself. Sequence: git pull -> install deps -> post "Deploy complete, restarting..." -> schedule restart after 2-second delay.

```python
async def _self_deploy(branch: str) -> str:
    """Deploy super_bot itself. Posts result then schedules restart."""
    # 1. git pull
    # 2. pip install
    # 3. Return success message (caller posts to Slack)
    # 4. Schedule: asyncio.get_event_loop().call_later(2, _restart_self)
    # The systemctl restart will kill this process; systemd auto-restarts it
```

- **Rollback = git checkout + redeploy.** `git reset --hard <ref>`, then same deps + restart flow. The ref can be a commit SHA, tag, or relative like `HEAD~1`. The bot should capture the current HEAD before rollback so it can report "rolled back from X to Y."

#### 2. `bot/log_reader.py` -- Log Access

Three log sources, all accessible locally on the VM:

```python
async def read_journald_logs(
    service: str = "superbot",
    lines: int = 50,
    grep: str | None = None,
    since: str | None = None,
) -> str:
    """Read systemd journal logs. Runs journalctl subprocess."""

async def read_prefect_flow_logs(flow_run_id: str) -> str:
    """Fetch logs for a specific Prefect flow run via API."""

async def read_app_logs(
    repo_name: str,
    lines: int = 50,
    grep: str | None = None,
) -> str:
    """Read application log files from repo directory."""
```

**Design decisions:**

- **journalctl runs locally** via `asyncio.create_subprocess_exec`. The bot runs as user `bot` which has sudo access for systemctl, so `sudo journalctl -u superbot -n 50 --no-pager` works directly.

- **Prefect flow logs via API.** Add `get_flow_run_logs(flow_run_id)` to `prefect_api.py`. The Prefect API endpoint is `GET /api/flow_runs/{id}/logs`.

- **Output truncation is mandatory.** Log output can be huge. Cap at 3000 characters for Slack (Slack messages max out around 4000 chars with mrkdwn). Truncate from the top (show most recent lines) with a "... (truncated, showing last N lines)" header.

- **Grep filter for journald.** Users will say "show me errors in the logs" -- translate to `journalctl -u superbot --no-pager -n 100 --grep="error"`. Parse the intent in fast_commands regex.

#### 3. `bot/health_ops.py` -- Bot Health Dashboard

Consolidates health info into a single fast-path response:

```python
async def get_health_dashboard() -> str:
    """Return formatted health dashboard string."""
    # Sources:
    # - task_state.get_uptime()
    # - queue_manager.get_state()
    # - background_monitor.get_active_monitors()
    # - Recent error count from journald (last hour)
    # - Current git commit SHA (version indicator)
```

**This largely extends the existing `_handle_bot_status` in fast_commands.py.** The current handler already shows queue state, background monitors, and uptime. The health dashboard adds:
- Current commit SHA + branch (version identification)
- Recent error count (grep journald for ERROR in last hour)
- Last successful agent run (from task_state recent tasks)

Whether this is a separate module or just an enhanced `_handle_bot_status` depends on complexity. Start by enhancing the existing handler; extract to `health_ops.py` only if it grows beyond ~80 lines.

#### 4. `bot/pipeline_ops.py` -- Pipeline Status

```python
async def get_pipeline_summary(
    hours: int = 24,
    status_filter: str | None = None,
) -> str:
    """Summarize recent Prefect flow runs."""
```

**Design decisions:**

- **Fast-path returns a summary table** of recent flow runs (last 24h by default): name, status, duration, start time. Formatted as a compact Slack message.

- **Agent handles deep investigation.** If the user says "why did the pipeline fail" or "investigate the DME crawl failure", that's an agent task, not a fast-path command. The fast-path only shows status.

- **Requires new `prefect_api.py` endpoint.** Add `list_recent_flow_runs(hours=24, limit=20)` using `POST /api/flow_runs/filter` with time-based filter.

### Data Flow for Each Feature

#### Deploy Flow
```
User: "deploy mic_transformer"
  -> fast_commands.py: matches _DEPLOY_RE
  -> deploy_ops.deploy_repo("mic_transformer")
    -> subprocess: git -C /home/bot/mic_transformer pull origin develop
    -> subprocess: /home/bot/mic_transformer/.venv/bin/pip install -r requirements.txt
    -> (no service restart for mic_transformer)
    -> subprocess: git -C /home/bot/mic_transformer log -1 --oneline
  -> Response: "Deployed mic_transformer: abc1234 (develop) -- 'fix extraction bug'"
```

#### Self-Deploy Flow (super_bot)
```
User: "deploy super_bot" / "deploy yourself"
  -> fast_commands.py: matches _DEPLOY_RE, repo=super_bot
  -> deploy_ops.deploy_repo("super_bot")
    -> subprocess: git pull origin main
    -> subprocess: pip install -r requirements.txt
    -> Post Slack: "Deploy complete. Restarting in 2s..."
    -> asyncio.get_event_loop().call_later(2, _restart_self)
    -> (bot process killed by systemd, auto-restarts on new code)
```

#### Rollback Flow
```
User: "rollback mic_transformer" / "rollback mic_transformer to abc1234"
  -> fast_commands.py: matches _ROLLBACK_RE
  -> deploy_ops.rollback_repo("mic_transformer", ref="HEAD~1" or "abc1234")
    -> capture current HEAD for reporting
    -> subprocess: git -C /path reset --hard <ref>
    -> subprocess: pip install -r requirements.txt (in case deps changed)
    -> (restart service if applicable)
  -> Response: "Rolled back mic_transformer from def5678 to abc1234"
```

#### Log Access Flow
```
User: "show me superbot logs" / "logs last 50 lines"
  -> fast_commands.py: matches _LOG_RE
  -> log_reader.read_journald_logs(service="superbot", lines=50)
    -> subprocess: sudo journalctl -u superbot -n 50 --no-pager
    -> truncate to 3000 chars
  -> Response: formatted log output in code block

User: "show errors in the logs"
  -> log_reader.read_journald_logs(grep="error")
    -> subprocess: sudo journalctl -u superbot -n 100 --no-pager --grep="error"

User: "prefect logs for run abc123"
  -> log_reader.read_prefect_flow_logs("abc123")
    -> prefect_api.get_flow_run_logs("abc123")
```

#### Health Dashboard Flow
```
User: "health" / "dashboard" / "bot health"
  -> fast_commands.py: enhanced _BOT_STATUS_RE or new _HEALTH_RE
  -> health_ops.get_health_dashboard()
    -> task_state.get_uptime()
    -> queue_manager.get_state()
    -> subprocess: git log -1 --format='%h %s'
    -> subprocess: sudo journalctl -u superbot --since '1 hour ago' --no-pager | grep -c ERROR
  -> Response: formatted dashboard
```

#### Pipeline Status Flow
```
User: "pipeline status" / "what ran today"
  -> fast_commands.py: matches _PIPELINE_RE
  -> pipeline_ops.get_pipeline_summary(hours=24)
    -> prefect_api.list_recent_flow_runs(hours=24)
  -> Response: formatted table of recent runs
```

### fast_commands.py Modifications

New entries added to `FAST_COMMANDS` list. Order matters:

```python
FAST_COMMANDS = [
    # Existing (unchanged)
    (_BATCH_CRAWL_RE, _handle_batch_crawl),
    (_EYEMED_CRAWL_RE, _handle_eyemed_crawl),
    (_EYEMED_STATUS_RE, _handle_eyemed_status),

    # New -- deploy/rollback (check before generic status)
    (_DEPLOY_RE, _handle_deploy),
    (_ROLLBACK_RE, _handle_rollback),
    (_DEPLOY_STATUS_RE, _handle_deploy_status),

    # New -- logs
    (_LOG_RE, _handle_logs),

    # New -- pipeline
    (_PIPELINE_RE, _handle_pipeline_status),

    # New -- health (more specific than bot status)
    (_HEALTH_RE, _handle_health),

    # Existing (unchanged, must be last -- catches broad status queries)
    (_BOT_STATUS_RE, _handle_bot_status),
]
```

Illustrative regex patterns:

```python
_DEPLOY_RE = re.compile(
    r"deploy\s+(super_?bot|mic.?transformer|irismed.?service|oso.?fe.?gsnap|oso.?desktop|yourself)",
    re.IGNORECASE,
)

_ROLLBACK_RE = re.compile(
    r"rollback\s+(super_?bot|mic.?transformer|irismed.?service|oso.?fe.?gsnap|oso.?desktop)",
    re.IGNORECASE,
)

_DEPLOY_STATUS_RE = re.compile(
    r"deploy\s+status|what.s\s+(?:running|deployed)|current\s+version",
    re.IGNORECASE,
)

_LOG_RE = re.compile(
    r"(?:show|get|read|tail)\s+(?:me\s+)?(?:the\s+)?(?:superbot\s+)?logs?"
    r"|logs?\s+(?:last|for|from|since)"
    r"|(?:superbot|bot)\s+logs?"
    r"|errors?\s+in\s+(?:the\s+)?logs?",
    re.IGNORECASE,
)

_PIPELINE_RE = re.compile(
    r"pipeline\s+status|what\s+ran\s+today|recent\s+(?:flow\s+)?runs?"
    r"|prefect\s+(?:status|summary|dashboard)",
    re.IGNORECASE,
)

_HEALTH_RE = re.compile(
    r"(?:bot\s+)?health(?:\s+check)?|dashboard|system\s+status",
    re.IGNORECASE,
)
```

## Patterns to Follow

### Pattern 1: Async Subprocess Execution
**What:** Use `asyncio.create_subprocess_exec` for all system commands (git, journalctl, pip).
**When:** Every deploy, rollback, and log operation.
**Why:** Already established in `fast_commands._run_script()` and `git_activity.py`. Keeps the event loop responsive.

```python
async def _run_cmd(
    cmd: list[str], cwd: str | None = None, timeout: int = 60,
) -> tuple[str, str, int]:
    """Run a command, return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode().strip(), stderr.decode().strip(), proc.returncode
```

### Pattern 2: Config-Driven Repo Registry
**What:** Centralize repo metadata (paths, services, venvs) in config.py.
**When:** Any operation that targets a specific repo.
**Why:** Avoids hardcoding paths in multiple places. Single source of truth for what's deployable.

### Pattern 3: Truncation-First Output
**What:** Always truncate command output before posting to Slack.
**When:** Log reading, deploy output, any subprocess output.
**Why:** Slack messages have practical limits (~4000 chars). Large outputs crash the formatter or get silently truncated by Slack.

```python
MAX_SLACK_OUTPUT = 3000

def _truncate(text: str, max_chars: int = MAX_SLACK_OUTPUT) -> str:
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    kept = []
    total = 0
    for line in reversed(lines):
        if total + len(line) + 1 > max_chars - 50:
            break
        kept.insert(0, line)
        total += len(line) + 1
    return f"... (showing last {len(kept)} of {len(lines)} lines)\n" + "\n".join(kept)
```

### Pattern 4: Slack Context Passthrough
**What:** Pass `slack_context` dict to handlers that need async follow-up messages.
**When:** Deploy operations that take >5 seconds (deps install, restart).
**Why:** Already established with batch crawl. Deploy might want to post progress ("Pulling...", "Installing deps...", "Restarting...") before the final result.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Using gcloud SSH from the Bot
**What:** Shelling out to `gcloud compute ssh` to reach the VM.
**Why bad:** The bot IS on the VM. gcloud SSH adds 3-5 seconds of overhead, requires gcloud auth on the VM, and creates a nested SSH session for no reason.
**Instead:** Run commands directly via `asyncio.create_subprocess_exec`.

### Anti-Pattern 2: Agent Pipeline for Deterministic Operations
**What:** Routing deploy/rollback/log requests through the Claude agent.
**Why bad:** Uses an agent turn (costs money, takes 30-60 seconds) for something that's a fixed sequence of shell commands. Blocks the single-threaded agent queue for the entire operation.
**Instead:** Fast-path commands handle the fixed logic directly.

### Anti-Pattern 3: Unbounded Log Output
**What:** Posting raw `journalctl -n 1000` output to Slack.
**Why bad:** Slack truncates or errors. Message becomes unreadable.
**Instead:** Default to 50 lines, truncate to 3000 chars, offer "use `logs last 200` for more."

### Anti-Pattern 4: Blocking Self-Restart
**What:** Running `sudo systemctl restart superbot` synchronously and expecting to report the result.
**Why bad:** The restart kills the bot process. The Slack response never gets posted.
**Instead:** Post the success message first, then schedule the restart with a 2-second delay using `asyncio.get_event_loop().call_later()`.

## Suggested Build Order

Build order is driven by dependency chains and incremental value delivery:

### Phase 1: Foundation (deploy_ops.py + config changes)
1. Add `DEPLOY_REPOS` registry to `config.py`
2. Create `bot/deploy_ops.py` with `deploy_repo()`, `rollback_repo()`, `get_deploy_status()`
3. Add deploy/rollback/deploy-status regexes and handlers to `fast_commands.py`
4. Test with non-service repos first (mic_transformer -- no restart needed)
5. Add self-deploy with delayed restart last

**Rationale:** Deploy is the highest-value feature and has no dependencies on other new modules. Testing is straightforward (deploy mic_transformer, verify git log shows new commit).

### Phase 2: Log Access (log_reader.py + prefect_api additions)
1. Create `bot/log_reader.py` with `read_journald_logs()` and truncation
2. Add `get_flow_run_logs()` to `prefect_api.py`
3. Add `read_prefect_flow_logs()` to `log_reader.py`
4. Add log regex and handler to `fast_commands.py`

**Rationale:** Depends on nothing from Phase 1. Could be built in parallel. Adds immediate observability value.

### Phase 3: Pipeline Status (pipeline_ops.py + prefect_api additions)
1. Add `list_recent_flow_runs()` to `prefect_api.py`
2. Create `bot/pipeline_ops.py` with `get_pipeline_summary()`
3. Add pipeline regex and handler to `fast_commands.py`

**Rationale:** Builds on prefect_api changes from Phase 2 (shared HTTP client patterns). Natural follow-on.

### Phase 4: Health Dashboard (health_ops.py or enhanced bot status)
1. Enhance `_handle_bot_status` in `fast_commands.py` or create `bot/health_ops.py`
2. Add git version, error count, optional system metrics
3. Add health regex to `fast_commands.py`

**Rationale:** Lowest complexity. Mostly assembles data from existing modules. Build last because it's the least urgent -- the existing bot status handler already covers the critical "is the bot alive?" question.

## Scalability Considerations

| Concern | Current (1 user) | At 5 users | Notes |
|---------|-------------------|------------|-------|
| Deploy concurrency | No issue | Could collide | Add a deploy lock (asyncio.Lock) to prevent concurrent deploys of the same repo |
| Log output size | Fine | Fine | Truncation handles this regardless of user count |
| Prefect API rate | Well within limits | Fine | Single Prefect instance, low request volume |
| Agent queue blocking | N/A (fast-path) | N/A | Ops commands bypass the agent queue entirely |

## Sources

- Existing codebase: `bot/fast_commands.py`, `bot/background_monitor.py`, `bot/prefect_api.py`, `bot/agent.py`, `bot/handlers.py`, `bot/queue_manager.py` (HIGH confidence -- primary sources)
- Existing deploy script: `scripts/deploy.sh` (HIGH confidence -- reference for deploy flow)
- Prefect API endpoints used in `prefect_api.py` (HIGH confidence)
- systemd service configuration inferred from deploy scripts and config references (HIGH confidence)
