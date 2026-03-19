# Phase 1: VM and Slack Bridge - Research

**Researched:** 2026-03-18
**Domain:** GCP VM provisioning (Terraform) + Slack Socket Mode bot (slack-bolt async)
**Confidence:** HIGH (core stack verified against official docs and PyPI; some Terraform specifics MEDIUM)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**VM Provisioning**
- Terraform for infrastructure-as-code in the existing IrisMed GCP project
- Ubuntu 24.04 LTS in us-west1 region
- Start with e2-small or e2-medium, resize as needed
- Startup script for auto-configuration (Python, git, clone repo, install deps)
- Dedicated low-privilege `bot` Linux user owns the repo clone and all bot files

**Credential Strategy**
- Two separate .env files:
  - Bot .env in bot home directory: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, GITLAB_TOKEN, ALLOWED_USERS
  - mic_transformer .env in repo clone directory: existing DB URLs, Prefect keys, service credentials
- No GCP Secret Manager — .env files on disk
- GitLab authentication via personal access token (HTTPS, not SSH)
- Claude Code CLI authentication via interactive `claude login` (one-time OAuth, stored in ~/.claude/)
- systemd service loads bot .env; mic_transformer .env available when Claude Code runs in that directory

**Slack Bot Identity**
- Bot name: SuperBot
- Channel: single channel only, configured via environment variable (decided at deploy time)
- Tone: minimal and professional — short status updates, results only, no personality
- On task received: add emoji reaction to the message AND post "Working on it." thread reply
- Error reporting: summary + key details (error message plus relevant context like file, line, command) — no full stack traces
- Completion messages include: what was done, files changed, links (MR/branch), duration
- Unauthorized users: silent ignore — bot appears offline to them
- User allowlist: ALLOWED_USERS env var with comma-separated Slack user IDs

**Slash Commands**
- `/status` — visible to all in channel, shows: current task, last 3-5 completed tasks, uptime/health, queue
- `/cancel` — visible to all, shows what's running and asks "Are you sure?" before killing
- `/help` — visible to all, shows what the bot can do and available commands

### Claude's Discretion
- Progress update strategy (edit one message vs post new replies) — Claude picks based on Slack rate limits
- Exact systemd unit file configuration
- Terraform module structure
- Startup script implementation details
- Event deduplication mechanism (in-memory vs file-based)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

> **IMPORTANT: INFRA-05 Conflict**
> REQUIREMENTS.md INFRA-05 says "GCP Secret Manager used for all credentials." The locked CONTEXT.md decision overrides this: credentials are stored in .env files on disk, no Secret Manager. The planner must implement INFRA-05 per the CONTEXT.md decision, not the requirements wording. The user deliberately chose .env files for simplicity.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | GCP VM provisioned with dedicated low-privilege bot user (not root) | Terraform `google_compute_instance` + startup script `useradd -m -s /bin/bash bot` — see Architecture Patterns |
| INFRA-02 | mic_transformer repository cloned on VM with full Python environment and dependencies | Startup script pattern: `git clone` via HTTPS personal access token, `uv venv`, `uv pip install -r requirements.txt` — see Code Examples |
| INFRA-03 | Claude Code CLI installed and authenticated with Anthropic API key on the VM | `npm install -g @anthropic-ai/claude-code` then one-time interactive `claude login` as bot user — see Architecture Patterns |
| INFRA-04 | systemd service configured for auto-restart with journald logging | `Restart=always`, `EnvironmentFile`, `User=bot`, `StandardOutput=journal` — full unit file in Code Examples |
| INFRA-05 | Credentials stored securely on disk (locked decision: .env files, no Secret Manager) | Two .env files: bot home dir + mic_transformer clone; `chmod 600`, owned by bot user — see Architecture Patterns |
| INFRA-06 | GitLab HTTPS token configured on VM for push/MR operations | GITLAB_TOKEN in bot .env; git remote set to `https://oauth2:${GITLAB_TOKEN}@gitlab.com/org/mic_transformer.git` — see Code Examples |
| SLCK-01 | Slack bot app created with Socket Mode (outbound WebSocket, no public URL) | App manifest with `socket_mode_enabled: true`, App Token (xapp-) with `connections:write` scope — see Standard Stack |
| SLCK-02 | Bot responds to @mentions in a designated team channel | `@app.event("app_mention")` with lazy listener pattern; channel filtered via `ALLOWED_CHANNEL` env var — see Architecture Patterns |
| SLCK-03 | Named-user allowlist restricts who can trigger the bot | Check `event["user"]` against `ALLOWED_USERS` env var (comma-separated Slack IDs); silent ignore if not in list — see Code Examples |
| SLCK-04 | Bot filters its own messages to prevent infinite response loops | Check `event.get("bot_id")` and `event.get("subtype") == "bot_message"` before processing — see Common Pitfalls |
| SLCK-05 | Lazy listener pattern: ACK within 3 seconds, process asynchronously | `@app.event("app_mention", lazy=[run_agent_task])` with async ack handler — see Architecture Patterns |
| SLCK-06 | Event deduplication prevents duplicate task execution on Slack retries | `cachetools.TTLCache` keyed on `event_id`, TTL=600s; Claude's Discretion for in-memory vs file — see Architecture Patterns |
| SLCK-07 | /status slash command shows currently running task and recent history | `@app.command("/status")` handler; reads from in-memory task state; posts ephemeral or in-channel — see Code Examples |
| SLCK-08 | /cancel slash command stops an in-flight Claude Code session | `@app.command("/cancel")` with confirmation step; cancels asyncio task; notifies channel — see Code Examples |
</phase_requirements>

---

## Summary

Phase 1 establishes the GCP VM and a correct Slack bridge. The two primary technical domains are: (1) Terraform-based GCP VM provisioning with a hardened bot user and systemd service, and (2) a Slack bot using `slack-bolt`'s `AsyncApp` with Socket Mode for real-time event handling.

The credential strategy is deliberately simple: two `.env` files on disk (one for bot config, one for mic_transformer), loaded by systemd and available to Claude Code via the working directory. This trades the operational complexity of GCP Secret Manager for simplicity appropriate to a 2-4 person team. Security is achieved through Linux file permissions (chmod 600) and the dedicated low-privilege `bot` user.

The Slack bot must implement three correctness-critical patterns from day one: (a) lazy listener / ack-first to avoid Slack's 3-second timeout, (b) bot-message self-filter to prevent infinite loops, and (c) event deduplication to prevent duplicate Claude invocations on Slack retries. These cannot be retrofitted — they must be correct in the first deployed version.

**Primary recommendation:** Use `slack-bolt` 1.27.0 with `AsyncApp` + `AsyncSocketModeHandler`, lazy listener pattern, `cachetools.TTLCache` for event deduplication, and a single `superbot.service` systemd unit loading the bot `.env` via `EnvironmentFile`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `slack-bolt` | 1.27.0 | Slack event handling, Socket Mode, slash commands | Official Slack SDK; handles signature verification, event routing, lazy listeners, async natively |
| `aiohttp` | 3.x latest | Async transport for AsyncSocketModeHandler | Required peer dependency of Bolt's async Socket Mode adapter |
| `cachetools` | 5.x | TTL-based in-memory cache for event deduplication | Lightweight, pure-Python; TTLCache with event_id as key prevents duplicate processing without Redis |
| `python-dotenv` | 1.x | Load .env files in the bot process | Reads the bot .env file at process start; used by systemd-launched service |
| Terraform (hashicorp/google provider) | ~> 5.x | GCP infrastructure provisioning | IaC; reproducible VM creation, networking, service account |
| systemd | OS-provided (Ubuntu 24.04) | Process management, auto-restart, journald logging | Already on the VM; no extra install; `Restart=always` handles crashes |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `structlog` | 24.x | Structured JSON logging | Correlate Slack `ts`, `event_id`, and task state in logs; easier to grep than plain logging |
| `uv` | latest | Fast venv + pip replacement | Use for all Python environment setup on the VM; faster and more reproducible than pip |

### Required Slack App Token Scopes

| Token Type | Scope | Purpose |
|------------|-------|---------|
| Bot Token (xoxb-) | `app_mentions:read` | Receive @mention events |
| Bot Token (xoxb-) | `chat:write` | Post messages and thread replies |
| Bot Token (xoxb-) | `reactions:write` | Add emoji reaction to triggering message |
| Bot Token (xoxb-) | `commands` | Register and handle slash commands |
| App Token (xapp-) | `connections:write` | Open and maintain Socket Mode WebSocket |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `cachetools.TTLCache` | File-based JSON event log | File-based survives process restart but adds I/O; for this scale, TTLCache is sufficient with the understanding that a fresh restart clears the cache (acceptable — Slack's retry window is 30 minutes) |
| `EnvironmentFile` in systemd | `Environment=` inline in unit | `EnvironmentFile` keeps secrets out of `systemctl show` output; use it |
| Terraform `metadata_startup_script` | Separate provisioner or Ansible | Startup script runs on first boot, embedded in Terraform; no extra tooling needed for single-VM setup |

**Installation:**
```bash
# On the VM, as root or via startup script
uv venv /home/bot/super_bot/.venv
source /home/bot/super_bot/.venv/bin/activate
uv pip install slack-bolt==1.27.0 aiohttp cachetools python-dotenv structlog
```

---

## Architecture Patterns

### Recommended Project Structure

```
super_bot/
├── bot/
│   ├── __init__.py
│   ├── app.py              # AsyncApp + AsyncSocketModeHandler entry point
│   ├── handlers.py         # app_mention lazy listener, slash command handlers
│   ├── access_control.py   # ALLOWED_USERS check, channel filter
│   ├── deduplication.py    # TTLCache-based event_id tracking
│   ├── task_state.py       # In-memory state: current task, recent history
│   └── formatter.py        # Format responses for Slack (plain text, minimal)
├── config.py               # Load .env, expose typed config values
├── requirements.txt
├── terraform/
│   ├── main.tf             # google_compute_instance, service account, firewall
│   ├── variables.tf
│   ├── outputs.tf
│   └── startup.sh          # VM bootstrap: user, git clone, venv, systemd install
└── systemd/
    └── superbot.service    # systemd unit file
```

### Pattern 1: Lazy Listener (Ack-First, Process Async)

**What:** Slack requires all events acknowledged within 3 seconds. The lazy listener pattern splits this into (a) immediate ack and (b) background processing via a separate `lazy` coroutine.

**When to use:** Always — mandatory for any handler that touches Claude Code (which takes 30+ seconds).

**Example:**
```python
# bot/handlers.py
# Source: https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/

@app.event("app_mention", lazy=[run_agent_task])
async def handle_mention_ack(ack, body, client, event):
    # Filter: ignore bot's own messages
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        await ack()
        return

    # Filter: check event deduplication
    event_id = body.get("event_id")
    if event_id and deduplication.is_seen(event_id):
        await ack()
        return

    # Filter: check authorized user
    user_id = event.get("user")
    if not access_control.is_allowed(user_id):
        await ack()
        return  # Silent ignore — bot appears offline to unauthorized users

    deduplication.mark_seen(event_id)
    await ack()
    # Post immediate acknowledgment
    await client.reactions_add(
        channel=event["channel"],
        name="hourglass_flowing_sand",
        timestamp=event["ts"]
    )
    await client.chat_postMessage(
        channel=event["channel"],
        thread_ts=event["ts"],
        text="Working on it."
    )


async def run_agent_task(body, client, event):
    # This runs in background — Phase 2 will implement Claude invocation here
    # Phase 1: just log and post placeholder
    thread_ts = event.get("thread_ts") or event["ts"]
    channel = event["channel"]
    task_state.set_current(body)
    # Claude invocation goes here in Phase 2
    await client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text="[Phase 1 stub: agent not yet connected]"
    )
```

### Pattern 2: Event Deduplication with TTLCache

**What:** Track `event_id` values in a TTL cache. If Slack retries an event (same `event_id`), the handler returns ack immediately without processing.

**When to use:** Always — in the ack handler, before any processing.

**Recommendation (Claude's Discretion):** Use `cachetools.TTLCache` with `maxsize=1000, ttl=600` (10 minutes). This covers Slack's retry window. In-memory is sufficient for a single-VM single-process bot. If the process restarts, the cache clears — acceptable because Slack's retry window is short relative to restart time, and Phase 1 tasks (Slack bridge only, no Claude) complete in under 1 second.

**Example:**
```python
# bot/deduplication.py
from cachetools import TTLCache
import threading

_cache = TTLCache(maxsize=1000, ttl=600)
_lock = threading.Lock()

def is_seen(event_id: str) -> bool:
    with _lock:
        return event_id in _cache

def mark_seen(event_id: str) -> None:
    with _lock:
        _cache[event_id] = True
```

### Pattern 3: Access Control via ALLOWED_USERS

**What:** Read comma-separated Slack user IDs from the `ALLOWED_USERS` environment variable. Check the `event["user"]` field before any processing. Silent ignore for unauthorized users.

**When to use:** In the ack handler — before deduplication marks the event as seen, so unauthorized retries also get silently dropped.

**Example:**
```python
# bot/access_control.py
import os

_allowed = set(os.environ.get("ALLOWED_USERS", "").split(","))

def is_allowed(user_id: str) -> bool:
    return user_id in _allowed and bool(user_id)
```

### Pattern 4: Slash Command Handlers

**What:** Register `/status`, `/cancel`, `/help` with `@app.command()`. These are handled separately from `app_mention` events. In Socket Mode, slash commands do NOT need a request URL in the app manifest — the WebSocket handles them.

**Example:**
```python
# bot/handlers.py

@app.command("/status")
async def handle_status(ack, respond, client, body):
    await ack()
    current = task_state.get_current()
    recent = task_state.get_recent(5)
    uptime = task_state.get_uptime()
    lines = [f"*SuperBot Status*"]
    if current:
        lines.append(f"Running: {current['text'][:80]}")
    else:
        lines.append("Idle")
    if recent:
        lines.append(f"Recent ({len(recent)}): " + " | ".join(r['text'][:40] for r in recent))
    lines.append(f"Uptime: {uptime}")
    await respond("\n".join(lines))


@app.command("/cancel")
async def handle_cancel(ack, respond):
    await ack()
    current = task_state.get_current()
    if not current:
        await respond("Nothing is running.")
        return
    await respond(
        f"Running: _{current['text'][:80]}_\n"
        "Reply `/cancel confirm` to stop it."
    )


@app.command("/help")
async def handle_help(ack, respond):
    await ack()
    await respond(
        "*SuperBot* — autonomous coding assistant for mic_transformer\n"
        "@mention me with a task to run Claude Code\n"
        "*/status* — current task, recent history, uptime\n"
        "*/cancel* — stop the current running task\n"
        "*/help* — this message"
    )
```

### Pattern 5: systemd Unit File

**What:** Manage the bot as a long-lived daemon. Auto-restart on crash. Load secrets from .env file.

**Recommendation (Claude's Discretion):** Use `EnvironmentFile` pointing to the bot's `.env` in the bot home directory. Run as the `bot` user. Use `StandardOutput=journal` and `StandardError=journal`. Use `Restart=always` with a 5-second restart delay.

**Example:**
```ini
# /etc/systemd/system/superbot.service

[Unit]
Description=SuperBot Slack Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=bot
Group=bot
WorkingDirectory=/home/bot/super_bot
EnvironmentFile=/home/bot/.env
ExecStart=/home/bot/super_bot/.venv/bin/python -m bot.app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=superbot

# Resource limits
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### Pattern 6: Terraform google_compute_instance

**What:** Provision the VM with infrastructure-as-code. Use startup script to bootstrap the bot user, clone repos, set up venv, and install systemd service.

**Key details:**
- Image family: `ubuntu-2404-lts`, project: `ubuntu-os-cloud` (MEDIUM confidence — verify with `gcloud compute images list --filter="name~ubuntu-24" --project=ubuntu-os-cloud` before applying)
- Machine type: `e2-small` (2 vCPU / 2 GB RAM) to start; `e2-medium` (2 vCPU / 4 GB RAM) if memory pressure observed
- Use `metadata_startup_script` (forces re-creation on script change — acceptable for initial setup; switch to `metadata.startup-script` if you want in-place updates later)
- Attach a dedicated service account with minimal scopes (no Secret Manager needed per locked decision)

**Example:**
```hcl
# terraform/main.tf

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = "us-west1"
}

resource "google_service_account" "superbot" {
  account_id   = "superbot-sa"
  display_name = "SuperBot Service Account"
}

resource "google_compute_instance" "superbot" {
  name         = "superbot-vm"
  machine_type = "e2-small"
  zone         = "us-west1-a"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts"
      size  = 20  # GB
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"
    access_config {}  # Ephemeral external IP
  }

  metadata_startup_script = file("${path.module}/startup.sh")

  service_account {
    email  = google_service_account.superbot.email
    scopes = ["cloud-platform"]
  }

  tags = ["superbot"]

  metadata = {
    enable-oslogin = "TRUE"
  }
}

resource "google_compute_firewall" "superbot_egress" {
  name    = "superbot-allow-egress"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["443", "80"]
  }

  direction     = "EGRESS"
  target_tags   = ["superbot"]
  destination_ranges = ["0.0.0.0/0"]
}
```

### Pattern 7: Startup Script

**What:** Bootstrap script run once on first boot. Creates bot user, clones repos, installs Python env, places systemd unit, starts service.

**Key order of operations:**
1. Create `bot` Linux user (no login shell capability, no sudo)
2. Install system packages (git, python3, npm for Claude Code)
3. Clone super_bot and mic_transformer repos as the bot user
4. Create venvs and install dependencies
5. Place systemd unit file and enable/start the service

**Note:** `.env` files must be placed manually after first boot (they contain secrets that cannot be in the startup script or Terraform state). The startup script creates placeholder `.env` files that the operator replaces on first SSH.

**Example skeleton:**
```bash
#!/bin/bash
# terraform/startup.sh
set -euo pipefail
exec > >(tee /var/log/startup.log) 2>&1

echo "=== SuperBot VM Bootstrap ==="

# 1. System packages
apt-get update -qq
apt-get install -y -qq git python3 python3-pip curl

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.cargo/bin:$PATH"

# Install Node.js for Claude Code CLI
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# 2. Create bot user
if ! id bot &>/dev/null; then
    useradd -m -s /bin/bash -c "SuperBot service user" bot
fi

# 3. Clone repos as bot user
sudo -u bot bash << 'BOT'
    cd /home/bot
    # super_bot repo
    git clone https://gitlab.com/irismed/super_bot.git super_bot
    # mic_transformer repo (token injected at deploy time — see DEPLOY.md)
    # git clone https://oauth2:${GITLAB_TOKEN}@gitlab.com/irismed/mic_transformer.git mic_transformer

    # Create venvs
    ~/.cargo/bin/uv venv /home/bot/super_bot/.venv
    source /home/bot/super_bot/.venv/bin/activate
    ~/.cargo/bin/uv pip install -r /home/bot/super_bot/requirements.txt

    # Placeholder .env — MUST be replaced manually before starting service
    cat > /home/bot/.env << 'ENV'
SLACK_BOT_TOKEN=REPLACE_ME
SLACK_APP_TOKEN=REPLACE_ME
GITLAB_TOKEN=REPLACE_ME
ALLOWED_USERS=REPLACE_ME
ALLOWED_CHANNEL=REPLACE_ME
ENV
    chmod 600 /home/bot/.env
BOT

# 4. Install Claude Code CLI as bot user (requires interactive login after)
sudo -u bot npm install -g @anthropic-ai/claude-code

# 5. Install and enable systemd service
cp /home/bot/super_bot/systemd/superbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable superbot
# Do NOT start yet — .env must be populated first
# systemctl start superbot

echo "=== Bootstrap complete. Populate /home/bot/.env then: systemctl start superbot ==="
```

### Anti-Patterns to Avoid

- **Responding synchronously to Slack events:** ACK must happen in < 3 seconds. Never run Claude Code inside the ack handler.
- **Subscribing to `message` events instead of `app_mention`:** The bot will receive every message in the channel, including its own, causing infinite loops.
- **Checking `bot_id` but not `subtype`:** Both fields can signal bot-authored messages; check both.
- **Using `continue_conversation=True` instead of explicit session IDs:** Breaks when two threads are active simultaneously — the SDK's "most recent" session is ambiguous.
- **Using `metadata_startup_script` for secrets:** The script content is visible in GCP metadata API. Place secrets via manual SSH after bootstrap, not in Terraform.
- **Running Claude Code as root:** Explicitly documented security violation. The `bot` user must be a non-root, low-privilege account.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slack signature verification | Custom HMAC validation | `slack-bolt` (built-in) | Bolt verifies `X-Slack-Signature` automatically on every request; timing-safe comparison included |
| Socket Mode WebSocket management | Custom WebSocket client | `AsyncSocketModeHandler` | Handles reconnection, heartbeats, ping/pong, and backoff automatically |
| Event routing by type | `if event_type == "app_mention"` dispatch | `@app.event()` decorator | Bolt handles routing, deserialization, error catching, and retry filtering |
| Slash command parsing | Parse raw Slack HTTP body | `@app.command()` decorator | Bolt parses the command body, handles ack, provides typed `body`, `respond` arguments |
| TTL-based deduplication cache | `dict` + manual expiry loop | `cachetools.TTLCache` | Thread-safe, auto-expiry, O(1) lookup; no background task needed |

**Key insight:** `slack-bolt` removes an entire class of correctness bugs (signature verification, event parsing, Socket Mode protocol) that are easy to get wrong. The framework is the standard for production Slack bots.

---

## Common Pitfalls

### Pitfall 1: Slack 3-Second Timeout

**What goes wrong:** Handler calls Claude Code before calling `ack()`. Slack retries the event. Duplicate Claude sessions start.

**Why it happens:** Developer builds the simplest path — receive event, run task, return result.

**How to avoid:** Always use `lazy=[...]` parameter on `@app.event()`. The `ack` function and lazy functions are separate.

**Warning signs:** Users see bot respond twice; Slack logs show `operation_timeout`; same `event_id` in logs multiple times.

### Pitfall 2: Bot Infinite Loop

**What goes wrong:** Bot posts a reply. The reply triggers another `app_mention`. Loop continues until rate-limited.

**Why it happens:** Missing `bot_id` check in the handler.

**How to avoid:** First check in every handler: `if event.get("bot_id") or event.get("subtype") == "bot_message": return await ack()`.

**Warning signs:** Bot replying to its own messages; Slack rate limit errors in logs; token spend spikes with no user activity.

### Pitfall 3: Slack Slash Command URLs in Manifest

**What goes wrong:** Developer adds request URLs to slash commands in the app manifest. These URLs are required for HTTP Events API mode but cause configuration confusion in Socket Mode (they're ignored but may trigger validation errors).

**How to avoid:** In Socket Mode, slash commands do NOT need a `url:` field in the manifest. The WebSocket handles all slash command payloads. Omit the URL entirely.

**Warning signs:** Manifest validation errors about slash command request URLs.

### Pitfall 4: .env File Permissions Too Permissive

**What goes wrong:** `.env` file readable by all users on the VM. Any process or user can read `SLACK_BOT_TOKEN` and impersonate the bot.

**How to avoid:** `chmod 600 /home/bot/.env && chown bot:bot /home/bot/.env`. Verify with `ls -la /home/bot/.env` after creation.

**Warning signs:** `ls -la` shows world-readable permissions.

### Pitfall 5: Ubuntu 24.04 LTS Image Family Name

**What goes wrong:** Using an incorrect image family name in Terraform causes apply failure or boots an unexpected OS version.

**How to avoid:** Verify the exact image family name before applying Terraform:
```bash
gcloud compute images list --filter="name~ubuntu-24" --project=ubuntu-os-cloud --sort-by=~creationTimestamp --limit=5
```
Expected family: `ubuntu-2404-lts` or `ubuntu-2404-lts-amd64`, project: `ubuntu-os-cloud`. (MEDIUM confidence — verify at plan time.)

**Warning signs:** Terraform apply fails with "image not found" error.

### Pitfall 6: Claude Code CLI Requires Interactive Login

**What goes wrong:** `claude login` is an interactive OAuth flow. It cannot run inside a startup script or systemd unit. If not performed manually, the bot starts but Claude Code invocations fail with auth errors.

**How to avoid:** Bootstrap installs the CLI. Operator SSHes in as the `bot` user and runs `claude login` interactively once. The credentials are stored in `~bot/.claude/` and persist across bot restarts (systemd service does not affect the `~/.claude/` directory).

**Warning signs:** Claude Code invocations fail with authentication errors after deployment.

### Pitfall 7: cachetools TTLCache Thread Safety

**What goes wrong:** `TTLCache` is not thread-safe by default. Concurrent Slack events (even at low volume) can corrupt the cache state.

**How to avoid:** Wrap all cache access in a `threading.Lock()` as shown in Pattern 2. Alternatively use `cachetools.func.lru_cache` which uses its own lock, or protect with `asyncio.Lock()` if using purely async code.

**Warning signs:** Occasional duplicate event processing despite deduplication being in place; Python `RuntimeError` in cache access.

---

## Code Examples

### AsyncApp Entry Point

```python
# bot/app.py
# Source: https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/
import asyncio
import os
from dotenv import load_dotenv
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from bot import handlers  # registers all @app.event and @app.command decorators

load_dotenv("/home/bot/.env")

app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])

# Register handlers (imported for side effects)
handlers.register(app)

async def main():
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()

if __name__ == "__main__":
    asyncio.run(main())
```

### Slack App Manifest (YAML)

```yaml
# Source: https://docs.slack.dev/reference/app-manifest/
_metadata:
  major_version: 2
  minor_version: 1

display_information:
  name: SuperBot

settings:
  socket_mode_enabled: true
  event_subscriptions:
    bot_events:
      - app_mention

features:
  bot_user:
    display_name: SuperBot
    always_online: false
  slash_commands:
    - command: /status
      description: Show current task, recent history, and uptime
    - command: /cancel
      description: Stop the currently running task
    - command: /help
      description: Show available commands

oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - reactions:write
      - commands
```

### Adding Emoji Reaction to Triggering Message

```python
# Source: https://docs.slack.dev/reference/methods/reactions.add/
await client.reactions_add(
    channel=event["channel"],
    name="hourglass_flowing_sand",   # or "eyes", "robot_face"
    timestamp=event["ts"]            # ts of the @mention message, not thread_ts
)
```

### Posting to Thread

```python
# Source: https://docs.slack.dev/tools/bolt-python/concepts/message-sending/
thread_ts = event.get("thread_ts") or event["ts"]
await client.chat_postMessage(
    channel=event["channel"],
    thread_ts=thread_ts,
    text="Working on it."
)
```

### GitLab HTTPS Authentication via Token

```bash
# In startup.sh, after GITLAB_TOKEN is in /home/bot/.env
# Store credentials so git operations don't prompt
sudo -u bot git config --global credential.helper store
sudo -u bot bash -c 'echo "https://oauth2:${GITLAB_TOKEN}@gitlab.com" > ~/.git-credentials'
chmod 600 /home/bot/.git-credentials

# Clone with token in URL
sudo -u bot git clone \
  "https://oauth2:${GITLAB_TOKEN}@gitlab.com/irismed/mic_transformer.git" \
  /home/bot/mic_transformer
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw `claude -p` subprocess with TTY | `claude-agent-sdk` Python package | Jan 2026 (SDK GA) | Eliminates TTY-hang bug; async-native API; bundles claude binary |
| Slack RTM API (WebSocket legacy) | Socket Mode via Events API | 2021 | RTM deprecated; Socket Mode is the current standard for apps without public URLs |
| Slack HTTP Events API + ngrok for dev | Socket Mode everywhere | 2021+ | Socket Mode works in dev and prod without URL infrastructure |
| pip + requirements.txt | `uv` for venv/install | 2024-2025 | 10-100x faster installs; lockfile support; drop-in replacement |
| Storing secrets in `.env` committed to git | GCP Secret Manager or .env outside repo | Ongoing | .env files are acceptable on disk if chmod 600, owned by service user, and not committed to git |

**Deprecated/outdated:**
- Slack RTM API: fully deprecated, do not use
- `websocket-client` for Slack (sync): use `aiohttp` + `AsyncSocketModeHandler` for async apps

---

## Open Questions

1. **GCP Project ID and existing service accounts**
   - What we know: The IrisMed GCP project exists; we're adding to it with Terraform
   - What's unclear: Whether there are existing Terraform state files, remote backends, or IAM constraints that need to be respected
   - Recommendation: Before writing `main.tf`, verify the GCP project ID and whether Terraform state is stored remotely (GCS bucket) or locally

2. **Ubuntu 24.04 LTS exact image family name on GCP**
   - What we know: Family is likely `ubuntu-2404-lts` in project `ubuntu-os-cloud`
   - What's unclear: GCP occasionally uses variant names like `ubuntu-2404-lts-amd64`
   - Recommendation: Run `gcloud compute images list --filter="name~ubuntu-24" --project=ubuntu-os-cloud` to confirm before applying Terraform

3. **mic_transformer repo clone URL**
   - What we know: Credentials via HTTPS personal access token; GitLab
   - What's unclear: Exact GitLab org/repo path for `mic_transformer`
   - Recommendation: Confirm the GitLab repo URL format before writing the startup script

4. **Slack workspace app creation**
   - What we know: App manifest YAML is ready; needs App-level token (xapp-) and Bot token (xoxb-)
   - What's unclear: Whether the Slack workspace has admin access available to create the app
   - Recommendation: Create the Slack app via api.slack.com/apps before or during planning; tokens are needed before the bot can be tested

5. **`/cancel confirm` two-step flow**
   - What we know: Phase 1 stub; no real agent to cancel yet
   - What's unclear: Slash commands in Socket Mode don't natively support multi-step confirmation flows; need to track "pending cancel" state per user
   - Recommendation: Phase 1 `/cancel` can show what's running and say "confirm not implemented yet — will send `/cancel confirm` in Phase 2." This avoids over-engineering a confirmation flow before there's anything to cancel.

---

## Sources

### Primary (HIGH confidence)
- `slack-bolt` PyPI 1.27.0 — https://pypi.org/project/slack-bolt/
- Slack Bolt Python Socket Mode docs — https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/
- Slack App Manifest reference — https://docs.slack.dev/reference/app-manifest/
- Slack reactions.add method — https://docs.slack.dev/reference/methods/reactions.add/
- Slack reactions:write scope — https://docs.slack.dev/reference/scopes/reactions.write/
- bolt-python socket_mode_async.py example — https://github.com/slackapi/bolt-python/blob/main/examples/socket_mode_async.py
- Terraform google_compute_instance docs — https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_instance
- `cachetools` PyPI — https://pypi.org/project/cachetools/

### Secondary (MEDIUM confidence)
- Ubuntu GCP image family naming (`ubuntu-2404-lts`) — multiple community sources agree; verify with gcloud at plan time
- e2-small (2 vCPU / 2 GB) and e2-medium (2 vCPU / 4 GB) specs — CloudPrice.net, corroborated by GCP docs structure
- Terraform startup_script file reference pattern — https://fabianlee.org/2021/05/28/terraform-invoking-a-startup-script-for-a-gce-google_compute_instance/
- Event deduplication with cachetools TTLCache — bolt-python GitHub issue #564, corroborated by multiple Slack bot guides

### Tertiary (LOW confidence)
- Exact Terraform `google_service_account` + `google_project_iam_member` resource syntax for the IrisMed project — not verified against the actual project; validate during planning

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — slack-bolt 1.27.0 and its async Socket Mode adapter are verified against official docs
- Architecture patterns: HIGH — lazy listener, event deduplication, and bot self-filter are documented Bolt patterns
- Terraform: MEDIUM — core resource structure is correct; Ubuntu 24.04 image family name needs CLI verification at plan time
- Pitfalls: HIGH — all critical pitfalls sourced from official Slack docs and known GitHub issues

**Research date:** 2026-03-18
**Valid until:** 2026-04-18 (slack-bolt and Terraform google provider change infrequently; check for new slack-bolt releases before planning)
