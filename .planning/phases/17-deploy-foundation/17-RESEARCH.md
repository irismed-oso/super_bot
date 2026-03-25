# Phase 17: Deploy Foundation - Research

**Researched:** 2026-03-25
**Domain:** Slack-driven deployment with self-restart, Prefect API integration, deploy-state persistence
**Confidence:** HIGH

## Summary

Phase 17 adds Slack-triggered deployment for super_bot and mic_transformer, plus verification of v1.4-v1.6 features on the VM. The codebase already has all the building blocks: the Prefect deploy pipeline (commit 08fa13f), the background monitor polling pattern, fast-command regex dispatch, edit-in-place messaging, and the queue manager with active-task detection.

The deploy command goes through the **agent pipeline** (not fast-path) per CONTEXT.md decisions, but deploy status/preview should be **fast-path commands** since they are read-only queries. The critical complexity is self-deploy: super_bot must write a deploy-state file before triggering the Prefect pipeline, then after systemd restarts the process, read that file on startup and post "I'm back" to the original Slack thread.

**Primary recommendation:** Implement deploy as an agent-pipeline task that calls the existing Prefect deploy API, with a deploy-state JSON file at `/home/bot/.deploy-state.json` for post-restart recovery. Add deploy status and deploy preview as fast-path commands.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Bot triggers deploy via the **Prefect deploy pipeline** (quick task 2), NOT direct git pull/systemctl
- Pre-restart message is detailed: shows current SHA -> target SHA, warns about restart, gives timeout guidance ("If I don't reply in 30s, check logs")
- Post-restart: bot checks for pending deploy-state file on startup, immediately posts "I'm back, running commit xyz" to the original thread
- Post-restart confirmation fires as soon as Slack connection is re-established (no delay for health check)
- Recovery on failure is manual SSH -- no auto-rollback mechanism for self-deploy
- For mic_transformer: poll Prefect API for completion (like batch crawl monitoring); for super_bot: deploy-state file checked on startup
- mic_transformer runs as a systemd service on the VM (service name TBD -- needs verification on VM)
- Deploy always pulls from main branch (no branch targeting)
- Accept both short aliases ("superbot", "mic") and full names ("super_bot", "mic_transformer")
- Deploy commands go through the **agent pipeline** (not fast-path)
- Deploy progress: single message **edited in place** as each step completes (like heartbeat updates)
- Deploy status: minimal -- commit hash + branch + "X commits behind"
- Active agent task blocks deploy with a warning; "deploy force [repo]" overrides
- If nothing to deploy (already on latest): abort with "Already on latest (abc1234). Nothing to deploy."
- Dirty state on VM: warn about uncommitted changes but proceed anyway

### Claude's Discretion
- Exact command regex patterns and aliases
- Deploy-state file format and location
- How to stash/handle dirty state during deploy
- mic_transformer health check implementation (once service name is known)

### Deferred Ideas (OUT OF SCOPE)
- Auto-rollback on failed self-deploy -- keeping manual for now, may add in Phase 18 (Rollback)
- Branch targeting ("deploy superbot branch feature-x") -- always main for now
- Deploy irismed-service and oso-fe-gsnap -- different infrastructure, paths undefined

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SDPL-01 | Deploy super_bot from Slack with self-restart and post-restart "I'm back" confirmation | Prefect deploy pipeline exists; deploy-state file pattern for post-restart recovery; app.py startup hook |
| SDPL-02 | Deploy mic_transformer from Slack with git pull, deps install, and health check | Prefect API client exists (prefect_api.py); background_monitor polling pattern for tracking completion |
| SDPL-03 | Deploy status showing current commit, branch, last deploy time, pending changes count | git subprocess commands; fast-path handler pattern in fast_commands.py |
| SDPL-04 | Deploy preview showing commits between current HEAD and origin/main | `git log HEAD..origin/main` after `git fetch`; fast-path handler |
| SDPL-05 | Deploy blocks if agent task running; "deploy force" overrides | queue_manager.get_current_task() exists; regex pattern with optional "force" keyword |
| VRFY-01 | Digest changelog verified working on VM | Manual verification during deploy workflow |
| VRFY-02 | Fast-path commands verified on VM | Manual verification during deploy workflow |
| VRFY-03 | Background task monitoring verified on VM | Manual verification during deploy workflow |
| VRFY-04 | Progress heartbeat verified on VM | Manual verification during deploy workflow |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | (already installed) | Async HTTP to Prefect API | Already used in prefect_api.py |
| asyncio | stdlib | Subprocess execution, background tasks | Already used throughout codebase |
| structlog | (already installed) | Structured logging | Already used throughout codebase |
| slack_bolt | (already installed) | Slack message editing (chat_update) | Already used for all Slack interaction |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | Deploy-state file serialization | Write/read deploy-state.json |
| subprocess (via asyncio) | stdlib | Git commands on VM | Deploy status, preview, commit SHA lookup |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Prefect API | Direct SSH/systemctl | Locked decision: must use Prefect pipeline |
| JSON deploy-state file | SQLite/DB | Over-engineering for single-field state |
| Agent pipeline for deploy | Fast-path | Locked decision: deploy goes through agent pipeline |

**Installation:**
```bash
# No new dependencies needed -- all libraries already in requirements.txt
```

## Architecture Patterns

### Recommended Project Structure
```
bot/
  deploy.py          # Deploy command handlers (agent-pipeline + fast-path)
  deploy_state.py    # Deploy-state file read/write + startup recovery
  fast_commands.py   # Add deploy status + preview fast-path entries
  app.py             # Add startup hook for deploy-state recovery
  handlers.py        # Wire deploy commands into agent pipeline
  queue_manager.py   # (existing) get_current_task() for active-task guard
  prefect_api.py     # (existing) Prefect API client -- may need deploy-specific methods
```

### Pattern 1: Deploy-State File for Self-Restart Recovery
**What:** Before super_bot triggers its own deploy (which will restart it), it writes a JSON file with the Slack thread context. On startup, the bot checks for this file, posts "I'm back" to that thread, and deletes the file.
**When to use:** Self-deploy only (super_bot deploys itself).
**Example:**
```python
# Deploy-state file: /home/bot/.deploy-state.json
{
    "channel": "C12345",
    "thread_ts": "1234567890.123456",
    "pre_sha": "abc1234",
    "triggered_at": "2026-03-25T10:30:00Z",
    "user_id": "U12345"
}
```

### Pattern 2: Prefect-Triggered Deploy with Polling (mic_transformer)
**What:** Trigger the deploy via Prefect API, then poll for completion status -- identical to the batch crawl background_monitor pattern.
**When to use:** mic_transformer deploys (bot stays alive, just polls).
**Example:**
```python
# Reuse existing prefect_api.find_deployment_id() and create_flow_run()
# Poll with prefect_api.get_flow_run_status() in a loop
# Edit progress message in-place with each status change
```

### Pattern 3: Agent Pipeline with Active-Task Guard
**What:** Deploy commands routed through the agent queue but with a pre-check: if `queue_manager.get_current_task()` returns a non-None value, the deploy is blocked unless "force" keyword is present.
**When to use:** All deploy commands.
**Note:** Since deploy commands go through the agent pipeline per CONTEXT.md, the active-task guard is naturally provided by the queue -- a deploy task will queue behind the running task. The explicit guard with "deploy force" is about **warning the user** that a task is running, not about queue mechanics. The guard should happen at the fast-command or handler level BEFORE enqueueing.

### Pattern 4: Deploy Status/Preview as Fast-Path
**What:** "deploy status" and "deploy preview" are read-only queries that run git commands as subprocesses and return formatted output. They follow the existing fast-path pattern (regex match, subprocess, edit ack message in-place).
**When to use:** Status and preview queries only -- actual deploys go through agent pipeline.
**Example:**
```python
# Fast-path regex for status
_DEPLOY_STATUS_RE = re.compile(
    r"deploy\s+(?:status|info)\s*(super_?bot|superbot|mic(?:_transformer)?)?",
    re.IGNORECASE,
)

# Fast-path regex for preview
_DEPLOY_PREVIEW_RE = re.compile(
    r"deploy\s+preview\s+(super_?bot|superbot|mic(?:_transformer)?)",
    re.IGNORECASE,
)
```

### Anti-Patterns to Avoid
- **Direct systemctl/SSH from bot code:** Locked decision says use Prefect pipeline. The bot should never SSH to itself or run `systemctl restart` directly.
- **Blocking the event loop during deploy:** Deploy polling must use asyncio tasks, never blocking calls.
- **Posting new messages for each step:** Locked decision says edit-in-place, like heartbeat.
- **Implementing deploy as fast-path:** CONTEXT.md says deploy goes through agent pipeline. Only status/preview are fast-path.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prefect API calls | Custom HTTP client | `bot/prefect_api.py` | Already has auth, error handling, async support |
| Background polling | Custom poll loop | Pattern from `bot/background_monitor.py` | Proven polling with progress updates |
| Message editing | Custom Slack API calls | `client.chat_update()` pattern from heartbeat.py | Already handles errors, formatting |
| Git commit info | Custom git parser | `asyncio.create_subprocess_exec(["git", ...])` | Simple subprocess, no library needed |
| Active task detection | Custom task tracking | `queue_manager.get_current_task()` | Already exists and works |
| Repo name resolution | Hardcoded if/else | Alias dict like LOCATION_ALIASES | Established pattern in fast_commands.py |

**Key insight:** Every pattern needed for Phase 17 already exists in the codebase -- deploy is essentially a combination of the Prefect API client, background monitor polling, fast-path command dispatch, and edit-in-place messaging.

## Common Pitfalls

### Pitfall 1: Deploy-State File Left Behind After Crash
**What goes wrong:** If the deploy fails and super_bot restarts without completing the deploy, the stale deploy-state file causes a false "I'm back" message on next restart.
**Why it happens:** systemd `Restart=always` with `RestartSec=5` means the bot will restart regardless of deploy success.
**How to avoid:** Include a `triggered_at` timestamp in the deploy-state file. On startup, if the file is older than 5 minutes, treat it as stale -- post a warning message instead of "I'm back" confirmation, or just delete it silently.
**Warning signs:** User sees "I'm back" but the deploy actually failed.

### Pitfall 2: Race Between Prefect Deploy and Bot Shutdown
**What goes wrong:** The bot triggers the Prefect deploy, which SSHes to the VM and runs `systemctl restart superbot`. The bot process dies mid-way through posting the pre-restart message.
**Why it happens:** The Prefect flow runs `restart-service` task which kills the bot process. If the pre-restart message post and deploy-state file write haven't completed, the post-restart recovery has no context.
**How to avoid:** Write the deploy-state file FIRST, then post the pre-restart message, then trigger Prefect. The deploy-state file is the source of truth, not the Slack message.
**Warning signs:** No "I'm back" message after a successful deploy.

### Pitfall 3: Git Fetch Required Before Preview
**What goes wrong:** "deploy preview" shows no commits because `git log HEAD..origin/main` uses a stale remote-tracking ref.
**Why it happens:** The VM's local repo doesn't automatically fetch from origin.
**How to avoid:** Run `git fetch origin main` before `git log HEAD..origin/main` in the preview handler.
**Warning signs:** Preview always shows "nothing to deploy" even when there are new commits.

### Pitfall 4: Slack Token Not Available on Startup for Post-Restart
**What goes wrong:** The bot reads the deploy-state file on startup but the Slack client isn't connected yet, so the "I'm back" message fails.
**Why it happens:** Deploy-state recovery runs before Socket Mode connection is established.
**How to avoid:** Schedule the recovery check AFTER `handler.start_async()` establishes the WebSocket connection, or use a brief delay/retry. The CONTEXT.md says "as soon as Slack connection is re-established" -- so tie it to connection readiness, not process startup.
**Warning signs:** Deploy completes successfully but no "I'm back" message appears.

### Pitfall 5: mic_transformer Prefect Deployment Name Unknown
**What goes wrong:** The code tries to find a Prefect deployment for mic_transformer but uses the wrong name.
**Why it happens:** We know the super_bot deployment is named "deploy-superbot" but mic_transformer's Prefect deployment name may be different or may not exist yet.
**How to avoid:** Make the deployment name configurable or discoverable. The Prefect deploy flow for mic_transformer may need to be created as a prerequisite.
**Warning signs:** "Deployment not found" errors when deploying mic_transformer.

## Code Examples

### Deploy-State File Write (before self-deploy)
```python
import json
import os
import time

DEPLOY_STATE_PATH = "/home/bot/.deploy-state.json"

def write_deploy_state(channel: str, thread_ts: str, pre_sha: str, user_id: str) -> None:
    """Write deploy-state file before triggering self-deploy."""
    state = {
        "channel": channel,
        "thread_ts": thread_ts,
        "pre_sha": pre_sha,
        "user_id": user_id,
        "triggered_at": time.time(),
    }
    with open(DEPLOY_STATE_PATH, "w") as f:
        json.dump(state, f)

def read_and_clear_deploy_state() -> dict | None:
    """Read and delete deploy-state file. Returns None if not found or stale."""
    if not os.path.isfile(DEPLOY_STATE_PATH):
        return None
    try:
        with open(DEPLOY_STATE_PATH) as f:
            state = json.load(f)
        os.unlink(DEPLOY_STATE_PATH)
        # Stale check: ignore if older than 5 minutes
        if time.time() - state.get("triggered_at", 0) > 300:
            return None
        return state
    except (json.JSONDecodeError, OSError):
        return None
```

### Post-Restart Recovery in app.py
```python
async def _check_deploy_recovery(client) -> None:
    """Check for pending deploy-state and post recovery message."""
    from bot.deploy_state import read_and_clear_deploy_state
    state = read_and_clear_deploy_state()
    if state is None:
        return
    # Get current commit SHA
    proc = await asyncio.create_subprocess_exec(
        "git", "rev-parse", "--short", "HEAD",
        stdout=asyncio.subprocess.PIPE,
        cwd="/home/bot/super_bot",
    )
    stdout, _ = await proc.communicate()
    current_sha = stdout.decode().strip()

    await client.chat_postMessage(
        channel=state["channel"],
        thread_ts=state["thread_ts"],
        text=f"I'm back, running commit `{current_sha}`.",
    )
```

### Deploy Status via Git Subprocess
```python
async def _get_deploy_status(repo_dir: str) -> dict:
    """Get deploy status info for a repo directory."""
    async def _git(*args):
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_dir,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()

    sha = await _git("rev-parse", "--short", "HEAD")
    branch = await _git("rev-parse", "--abbrev-ref", "HEAD")
    # Fetch to get accurate behind count
    await _git("fetch", "origin", "main", "--quiet")
    behind = await _git("rev-list", "--count", "HEAD..origin/main")

    return {"sha": sha, "branch": branch, "behind": int(behind)}
```

### Repo Name Alias Resolution
```python
REPO_ALIASES = {
    "superbot": ("super_bot", "/home/bot/super_bot"),
    "super_bot": ("super_bot", "/home/bot/super_bot"),
    "mic": ("mic_transformer", "/home/bot/mic_transformer"),
    "mic_transformer": ("mic_transformer", "/home/bot/mic_transformer"),
}

def resolve_repo(text: str) -> tuple[str, str] | None:
    """Resolve a repo name/alias to (canonical_name, directory_path)."""
    for alias, info in REPO_ALIASES.items():
        if alias in text.lower():
            return info
    return None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| scripts/deploy.sh (local SSH) | Prefect deploy pipeline | Quick task 2 (2026-03-25) | No gcloud auth needed; can trigger from anywhere |
| scripts/deploy_via_prefect.py (CLI) | Slack-triggered deploy (this phase) | Phase 17 | Nicole can deploy from Slack without terminal |

**Existing infrastructure that enables Phase 17:**
- `prefect/deploy_superbot_flow.py` -- Prefect flow that SSHes to VM, pulls, installs, restarts
- `scripts/deploy_via_prefect.py` -- CLI that finds deployment, creates flow run, polls status
- `bot/prefect_api.py` -- Async Prefect API client with auth
- `bot/background_monitor.py` -- Polling loop pattern for Prefect flow runs
- systemd `Restart=always RestartSec=5` -- Bot auto-restarts after deploy

## Open Questions

1. **mic_transformer Prefect deployment name**
   - What we know: super_bot has `deploy-superbot` deployment. mic_transformer may need its own deploy flow.
   - What's unclear: Does a `deploy-mic-transformer` Prefect deployment exist? If not, it needs to be created.
   - Recommendation: Check Prefect API for existing deployments. If none exists, create `prefect/deploy_mic_transformer_flow.py` as part of this phase.

2. **mic_transformer systemd service name**
   - What we know: CONTEXT.md says "service name TBD -- needs verification on VM"
   - What's unclear: What is the actual service name? Is it `mic-transformer`, `mic_transformer`, or something else?
   - Recommendation: The planner should include a task to verify this on the VM before implementing mic_transformer deploy. This may be a manual step.

3. **VRFY-01 through VRFY-04 execution method**
   - What we know: These require verifying v1.4-v1.6 features work on the production VM.
   - What's unclear: Whether these should be automated checks in the deploy workflow or manual verification steps documented in a runbook.
   - Recommendation: Implement as manual verification with a checklist in DEPLOY.md. Automating would require test infrastructure that doesn't exist.

4. **Deploy command routing: agent vs fast-path**
   - What we know: CONTEXT.md says "deploy commands go through the agent pipeline." But STATE.md says "v1.8: All ops commands implemented as fast-path handlers (no agent pipeline)."
   - What's unclear: There's a contradiction. CONTEXT.md is phase-specific and more recent.
   - Recommendation: Follow CONTEXT.md (agent pipeline for actual deploys). Status/preview can be fast-path since they're read-only. But this should be flagged for the planner to address.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `bot/fast_commands.py`, `bot/handlers.py`, `bot/queue_manager.py`, `bot/prefect_api.py`, `bot/background_monitor.py`, `bot/heartbeat.py`, `bot/app.py`
- `prefect/deploy_superbot_flow.py` -- existing Prefect deploy flow
- `scripts/deploy_via_prefect.py` -- existing CLI deploy script
- `systemd/superbot.service` -- systemd configuration (Restart=always, RestartSec=5)
- `.planning/phases/17-deploy-foundation/17-CONTEXT.md` -- locked decisions

### Secondary (MEDIUM confidence)
- `DEPLOY.md` -- deployment runbook and existing patterns

### Tertiary (LOW confidence)
- mic_transformer Prefect deployment existence -- unverified, needs VM check

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- all patterns proven in existing codebase (background_monitor, fast_commands, heartbeat)
- Pitfalls: HIGH -- derived from analyzing actual code paths (systemd restart timing, Slack connection lifecycle, git fetch requirement)
- Deploy-state recovery: MEDIUM -- pattern is sound but timing of Slack client readiness needs validation

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable -- internal tooling, no external API changes expected)
