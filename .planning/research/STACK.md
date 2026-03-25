# Technology Stack

**Project:** SuperBot v1.8 Production Ops
**Researched:** 2026-03-25
**Confidence:** HIGH

---

## Existing Stack (NOT re-researched)

Already validated and running in production:

| Technology | Version | Purpose |
|------------|---------|---------|
| `claude-agent-sdk` | 0.1.49 | Claude Code agent engine |
| `slack-bolt` | 1.27.0 | Slack event handling (Socket Mode, lazy listener) |
| `httpx` | (installed) | Async HTTP client for Prefect API |
| `structlog` | >=24.0 | Structured logging |
| `asyncio.create_subprocess_exec` | stdlib | Shell command execution (git, scripts) |
| `asyncpg` | >=0.29 | PostgreSQL session/message logging |
| `cachetools` | >=5.0 | Event deduplication TTL cache |
| `aiohttp` | >=3.9 | Slack SDK transport layer |
| Python | 3.10 | Runtime on VM |
| systemd / journald | OS-provided | Process management and logging |
| `gcloud compute ssh` | installed | SSH to VM (used by deploy.sh) |

---

## New Stack for v1.8: Nothing

**No new Python packages are needed.** Every v1.8 feature can be built with the existing stack.

This is because:
1. **Deploy from Slack** -- The bot runs ON the GCP VM. Deploy = `git pull` + `pip install` + `systemctl restart`. All executable via `asyncio.create_subprocess_exec` (already used in `fast_commands.py`, `worktree.py`, `digest_changelog.py`, `git_activity.py`).
2. **Git-based rollback** -- `git log`, `git checkout`, `git reset` via subprocess. Same pattern as existing git operations in `worktree.py` and `git_activity.py`.
3. **Journald log access** -- `journalctl -u <service> -n <lines> --no-pager` via subprocess. No Python wrapper needed.
4. **Prefect flow logs** -- `POST /api/logs/filter` with `flow_run_id` filter. Already using `httpx.AsyncClient` in `prefect_api.py`.
5. **App log access** -- `tail -n <lines> <logfile>` via subprocess, or read file directly.
6. **Bot health dashboard** -- Already has `task_state.py` with uptime, current task, recent tasks, queue state. Extend in-memory state, no new deps.
7. **Pipeline status** -- Prefect API flow run filtering already implemented. Extend `prefect_api.py`.

---

## Integration Points for New Features

### Deploy from Slack (All 4 Repos)

**Pattern:** New fast-path commands using `asyncio.create_subprocess_exec`.

Each repo deploy follows the same steps, all executable locally on the VM:

```python
# Step 1: git pull (already have this pattern in git_activity.py)
proc = await asyncio.create_subprocess_exec(
    "git", "pull", "origin", branch,
    cwd=repo_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)

# Step 2: pip install (same pattern)
proc = await asyncio.create_subprocess_exec(
    f"{repo_path}/.venv/bin/pip", "install", "-r", "requirements.txt",
    cwd=repo_path, ...
)

# Step 3: systemctl restart (requires sudo)
proc = await asyncio.create_subprocess_exec(
    "sudo", "systemctl", "restart", service_name, ...
)

# Step 4: health check (systemctl is-active)
proc = await asyncio.create_subprocess_exec(
    "sudo", "systemctl", "is-active", service_name, ...
)
```

**Repo config needed** (add to `config.py`):

```python
# v1.8: Deploy targets -- repo name -> (path, service_name, branch)
DEPLOY_TARGETS: dict[str, dict] = {
    "super_bot": {
        "path": "/home/bot/super_bot",
        "service": "superbot",
        "branch": "main",
        "python": "/home/bot/super_bot/.venv/bin/python",
    },
    "mic_transformer": {
        "path": "/home/bot/mic_transformer",
        "service": "mic-transformer",  # or None if no systemd service
        "branch": "develop",
        "python": "/home/bot/mic_transformer/.venv/bin/python",
    },
    "irismed_service": {
        "path": "/home/bot/irismed-service",
        "service": "irismed",
        "branch": "develop",
        "python": "/home/bot/irismed-service/.venv/bin/python",
    },
    "oso_fe_gsnap": {
        "path": "/home/bot/oso-fe-gsnap",
        "service": "oso-fe",
        "branch": "develop",
        "python": "/home/bot/oso-fe-gsnap/.venv/bin/python",
    },
}
```

**Sudo access:** The `bot` user needs passwordless sudo for `systemctl restart/status/is-active <service>`. Add to `/etc/sudoers.d/bot`:
```
bot ALL=(root) NOPASSWD: /usr/bin/systemctl restart superbot, /usr/bin/systemctl restart mic-transformer, ...
bot ALL=(root) NOPASSWD: /usr/bin/systemctl status superbot, /usr/bin/systemctl status mic-transformer, ...
bot ALL=(root) NOPASSWD: /usr/bin/systemctl is-active superbot, /usr/bin/systemctl is-active mic-transformer, ...
bot ALL=(root) NOPASSWD: /usr/bin/journalctl -u *
```

### Journald Log Access

**Pattern:** subprocess call to `journalctl`.

```python
# Tail last N lines for a service
proc = await asyncio.create_subprocess_exec(
    "sudo", "journalctl", "-u", service, "-n", str(lines), "--no-pager",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)

# Filter by time range
proc = await asyncio.create_subprocess_exec(
    "sudo", "journalctl", "-u", service,
    "--since", since_str,  # e.g. "1 hour ago", "2026-03-25 10:00"
    "--no-pager",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)

# Grep for pattern
proc = await asyncio.create_subprocess_exec(
    "sudo", "journalctl", "-u", service, "--no-pager", "-g", pattern,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

**Sudo access:** journalctl needs root to read other services' logs. Add to sudoers (see above).

### Prefect Flow Run Logs

**Pattern:** Extend existing `prefect_api.py` with new method using existing `httpx.AsyncClient`.

```python
async def get_flow_run_logs(
    flow_run_id: str, limit: int = 100, level_ge: int = 0
) -> list[dict]:
    """Fetch logs for a specific flow run from Prefect API."""
    async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{PREFECT_API}/logs/filter",
            json={
                "logs": {
                    "flow_run_id": {"any_": [flow_run_id]},
                    "level": {"ge_": level_ge},
                },
                "sort": "TIMESTAMP_ASC",
                "limit": min(limit, 100),  # Prefect enforces max 100
            },
        )
        resp.raise_for_status()
        return resp.json()
```

### Bot Health Dashboard

**Pattern:** Extend existing `task_state.py` and add new fast-path command.

New data points to track (all in-memory, no new deps):
- Error count since boot (increment in exception handlers)
- Last error timestamp and message
- Last successful task timestamp
- Memory usage (`os.getpid()` + read `/proc/self/status` or `resource.getrusage`)
- Active background monitors (already tracked in `background_monitor.py`)

```python
import resource
import os

def get_memory_mb() -> float:
    """RSS in MB via stdlib resource module."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KB -> MB
```

### Pipeline Status

**Pattern:** Extend `prefect_api.py` to query recent flow runs.

```python
async def get_recent_flow_runs(
    hours_back: int = 24, limit: int = 20
) -> list[dict]:
    """Get recent flow runs across all deployments."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{PREFECT_API}/flow_runs/filter",
            json={
                "flow_runs": {
                    "start_time": {"after_": since},
                },
                "sort": "START_TIME_DESC",
                "limit": limit,
            },
        )
        resp.raise_for_status()
        return resp.json()
```

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `paramiko` or `fabric` for SSH | Bot runs on the same VM as the repos. No SSH needed for deploy. | `asyncio.create_subprocess_exec` with local commands |
| `psutil` for process monitoring | Heavyweight dependency for simple health checks | `resource.getrusage()` (stdlib) + `/proc/self/status` reads |
| `systemd-python` or `pystemd` bindings | Adds native compilation dependency, harder to install | Shell out to `systemctl` / `journalctl` via subprocess |
| `python-prefect` client library | Massive dependency tree, overkill for 3-4 REST API calls | `httpx` (already installed) with direct API calls |
| New database tables for deploy history | Over-engineering for a 2-person team | In-memory list of recent deploys (same pattern as `task_state._recent_tasks`) |
| Web dashboard framework (Flask, FastAPI) | Out of scope -- Slack is the interface | Fast-path commands returning formatted Slack messages |
| `asyncssh` for remote operations | No remote operations needed -- bot is local | Direct subprocess execution |
| Log aggregation service (Loki, CloudWatch) | Over-engineering for single-VM setup | `journalctl` subprocess + Prefect API |

---

## Config Additions Required

### config.py Changes

```python
# v1.8: Deploy targets (env var or hardcoded)
# Format: repo_name:path:service:branch (comma-separated entries)
DEPLOY_TARGETS_RAW: str = os.environ.get(
    "DEPLOY_TARGETS",
    "super_bot:/home/bot/super_bot:superbot:main,"
    "mic_transformer:/home/bot/mic_transformer:mic-transformer:develop,"
    "irismed_service:/home/bot/irismed-service:irismed:develop,"
    "oso_fe_gsnap:/home/bot/oso-fe-gsnap:oso-fe:develop"
)
```

### VM Sudoers Changes

The `bot` user needs passwordless sudo for exactly these commands:
- `systemctl restart|status|is-active <service>` for each deploy target
- `journalctl -u <service>` for log access

This is a one-time manual setup on the VM, not a code change.

---

## Existing Patterns to Reuse

| Pattern | Where Used Today | Reuse For |
|---------|------------------|-----------|
| `asyncio.create_subprocess_exec` + timeout | `fast_commands._run_script()` | Deploy commands, journalctl, git operations |
| Fast-path regex + handler | `fast_commands.FAST_COMMANDS` list | Deploy, logs, health, pipeline status commands |
| `httpx.AsyncClient` with Prefect auth | `prefect_api.py` | Flow run logs, pipeline status queries |
| In-memory state with recent history | `task_state.py` | Deploy history, error tracking |
| Background task with progress updates | `background_monitor.py` | Deploy progress (pull/install/restart phases) |
| Slack message formatting | `formatter.py` | Deploy results, log output, health dashboard |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| Deploy mechanism | Local subprocess (git/pip/systemctl) | Ansible/Terraform | Bot is ON the VM. Running local commands is simpler, faster, zero additional deps. |
| Log access | journalctl subprocess | Structured log files + Python file I/O | journalctl already aggregates all systemd services, supports filtering, time ranges, grep. Reimplementing in Python adds no value. |
| Process health | `resource.getrusage()` + systemctl | `psutil` | Avoids adding a compiled dependency. getrusage covers RSS; systemctl covers service state. |
| Prefect API client | Direct `httpx` calls | `prefect` Python SDK | The SDK pulls in 100+ transitive dependencies. We need 3-4 endpoints. httpx is already working. |
| Deploy history storage | In-memory list | PostgreSQL table | 2-person team, deploys are infrequent. In-memory with last-5 is sufficient. If the bot restarts, deploy history loss is acceptable. |
| Self-deploy (super_bot) | Sequential: pull, install, restart (self-kill) | Blue-green or rolling | Single-instance bot. Self-restart via systemctl is fine -- systemd will restart the new version. 2-3 second downtime is acceptable for an internal tool. |

---

## Version Compatibility

No new packages, so no new compatibility concerns. Existing stack remains pinned:

| Package | Version | Constraint |
|---------|---------|------------|
| `slack-bolt` | 1.27.0 | Pinned in requirements.txt |
| `claude-agent-sdk` | 0.1.49 | Pinned in requirements.txt |
| `httpx` | (transitive) | Via aiohttp/claude-agent-sdk |
| `structlog` | >=24.0,<25.0 | Range-pinned in requirements.txt |
| `asyncpg` | >=0.29,<1.0 | Range-pinned in requirements.txt |

---

## Self-Deploy Consideration

When SuperBot deploys itself (`super_bot` repo), the process is:
1. `git pull origin main` -- updates code on disk
2. `pip install -r requirements.txt` -- updates deps if changed
3. `sudo systemctl restart superbot` -- kills current process, systemd starts new one

Step 3 kills the running bot mid-response. The Slack message confirming success will never be sent. Mitigations:
- Post "Restarting now..." message BEFORE issuing `systemctl restart`
- After restart, the new bot process could check for a "pending deploy confirmation" marker file and post success
- Or simply: the user sees the bot go offline briefly, then come back. Acceptable UX for internal tool.

---

## Sources

- Prefect REST API `/logs/filter` endpoint: [Prefect REST API Reference](https://docs.prefect.io/latest/api-ref/rest-api-reference/)
- Existing `prefect_api.py` implementation: verified from `bot/prefect_api.py` (httpx + basic auth pattern)
- Existing subprocess pattern: verified from `bot/fast_commands.py:54-73`, `bot/worktree.py:48-73`, `bot/git_activity.py:107-148`
- Existing deploy script: verified from `scripts/deploy.sh` (gcloud SSH + git pull + pip + systemctl + health check)
- Python `resource` module: [Python stdlib docs](https://docs.python.org/3/library/resource.html) -- `getrusage(RUSAGE_SELF).ru_maxrss`
- Existing config pattern: verified from `config.py` (env var with parsing)
- Existing fast-path pattern: verified from `bot/fast_commands.py` (regex + async handler registry)

---
*Stack research for: SuperBot v1.8 Production Ops -- deploy, rollback, logs, health, pipeline status*
*Researched: 2026-03-25*
