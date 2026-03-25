# SuperBot Deployment Runbook (Phase 1)

Step-by-step guide for the first deployment. Follow all steps in order.

## Prerequisites

Before starting, ensure you have:

- GCP project ID (the IrisMed project)
- GitLab personal access token with read/write repo access for `super_bot` and `mic_transformer`
- Slack workspace admin access to create an app
- Anthropic API key (for `claude login`)
- `gcloud` CLI installed and authenticated
- `terraform` CLI installed (v1.5+)

## Step 1: Verify GCP Image Family Name

```bash
gcloud compute images list --filter="name~ubuntu-24" --project=ubuntu-os-cloud --sort-by=~creationTimestamp --limit=5
```

Confirm the family name is `ubuntu-2404-lts`. If different, update the `image_family` variable default in `terraform/variables.tf` before proceeding.

## Step 2: Create the Slack App

1. Go to https://api.slack.com/apps and click **Create New App**.
2. Choose **From an app manifest**.
3. Select the IrisMed Slack workspace.
4. Paste the contents of `slack_manifest.yaml` from this repo.
5. Review and create the app.
6. From **Basic Information**, enable **Socket Mode** and generate an **App-Level Token** with the `connections:write` scope. This is your `SLACK_APP_TOKEN` (starts with `xapp-`).
7. From **OAuth & Permissions**, install the app to the workspace. This gives you the **Bot Token** (`SLACK_BOT_TOKEN`, starts with `xoxb-`).
8. Invite the bot to the target channel: type `/invite @SuperBot` in that channel.
9. Get the channel ID: right-click the channel name, select **Copy link**. The ID is the segment after the last `/` (starts with `C`).
10. Get your Slack user ID: click your profile, select **Copy member ID** (starts with `U`). Do the same for any other allowed users.

Save these values; you will need them in Step 4:
- `SLACK_BOT_TOKEN` (xoxb-...)
- `SLACK_APP_TOKEN` (xapp-...)
- Channel ID (C...)
- User IDs (U...)

## Step 3: Run Terraform

```bash
cd terraform/
terraform init
terraform plan -var="gcp_project=YOUR_GCP_PROJECT_ID"
# Review the plan -- should show 3 resources to create
terraform apply -var="gcp_project=YOUR_GCP_PROJECT_ID"
# Note the vm_external_ip output
```

Wait for Terraform to complete. The VM will begin running its startup script automatically.

## Step 4: SSH to the VM and Populate .env

Wait 2-3 minutes for the startup script to finish, then verify:

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "tail -f /var/log/startup.log"
# Wait until you see "Bootstrap complete" in the log, then Ctrl+C
```

Populate the bot .env file with the tokens from Step 2:

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a << 'EOF'
cat > /home/bot/.env << 'ENV'
SLACK_BOT_TOKEN=xoxb-YOUR-BOT-TOKEN
SLACK_APP_TOKEN=xapp-YOUR-APP-TOKEN
GITLAB_TOKEN=YOUR-GITLAB-PAT
ALLOWED_USERS=U_NICOLE_ID,U_HAN_ID
ALLOWED_CHANNEL=C_CHANNEL_ID
ENV
chmod 600 /home/bot/.env
EOF
```

Replace the placeholder values with your actual tokens and IDs.

## Step 5: Configure GitLab Credentials

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo -u bot bash -c '
    source /home/bot/.env
    echo \"https://oauth2:\${GITLAB_TOKEN}@gitlab.com\" > /home/bot/.git-credentials
    chmod 600 /home/bot/.git-credentials
    git config --global credential.helper store
  '
"
```

## Step 6: Clone mic_transformer as Bot User

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo -u bot bash -c '
    source /home/bot/.env
    git clone \"https://oauth2:\${GITLAB_TOKEN}@gitlab.com/irismed/mic_transformer.git\" /home/bot/mic_transformer
  '
"
```

Update the GitLab org/repo path if different from `irismed/mic_transformer`.

## Step 7: Interactive Claude Login (One-Time)

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a
# On the VM:
sudo -u bot bash
claude login
# Follow the OAuth flow in your browser
# Credentials are stored in ~/.claude/ and persist across service restarts
exit
exit
```

## Step 8: Start the Service

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo systemctl start superbot
  sudo systemctl status superbot
"
```

Expected output: `active (running)`.

## Step 9: Check Logs

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo journalctl -u superbot -f --lines=50
"
```

Expected: No authentication errors, Socket Mode connection established. Press Ctrl+C to stop tailing.

## Deploying Updates (Any Milestone)

Use this section for all subsequent deployments after the initial Phase 1 setup. The deploy script handles code deployment -- push, pull, restart, and health check -- in one command.

**When to use:** After any code changes are committed and ready to deploy to the VM.

### Quick Deploy

```bash
bash scripts/deploy.sh
```

This pushes the current branch to origin, SSHs to the VM, pulls the latest code, installs Python dependencies, restarts the service, and verifies health.

### Options

| Flag | Description |
|------|-------------|
| `--branch BRANCH` | Deploy a specific branch (default: pushes and deploys current branch) |
| `--skip-push` | Skip git push (if already pushed) |
| `--skip-deps` | Skip pip install (for code-only changes with no new dependencies) |

### Examples

```bash
# Full deploy (push + deps + restart)
bash scripts/deploy.sh

# Code-only deploy (no pip install)
bash scripts/deploy.sh --skip-deps

# Already pushed, just deploy
bash scripts/deploy.sh --skip-push

# Deploy a specific branch
bash scripts/deploy.sh --branch feature-x
```

### What It Does

1. Pushes current branch to origin (unless `--skip-push`)
2. SSHs to VM, pulls latest code
3. Installs Python dependencies via `uv pip install` (unless `--skip-deps`)
4. Restarts the `superbot` systemd service
5. Runs health check (service status + crash detection in logs)

### Post-Deploy Verification

Send `@SuperBot hello` in the Slack channel. Expected: response within 30 seconds.

### Note

For milestone-specific setup (new env vars, new repos, new services), see the version-specific sections below. The deploy script only handles code deployment.

## Deploy via Prefect (No gcloud auth needed)

This method triggers a Prefect flow running on the VM. No SSH, no `gcloud auth login`, no VPN -- just network access to the Prefect server.

The flow performs the same steps as `scripts/deploy.sh`: git pull, install dependencies, restart service, and health check.

### Prerequisites

- Network access to `136.111.85.127:4200` (the Prefect server)
- Python 3.10+

### One-Time Setup (on VM)

The deploy flow must be running on the VM so Prefect can execute it. SSH once to start it:

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo -u bot bash -c '
    cd /home/bot/super_bot
    source .venv/bin/activate
    nohup python prefect/deploy_superbot_flow.py > /tmp/deploy-flow.log 2>&1 &
  '
"
```

This registers the `deploy-superbot` deployment with Prefect and keeps the flow served. It only needs to run once (or after VM reboot).

### Usage

```bash
# Deploy main branch (pushes first, installs deps, restarts, health checks)
python scripts/deploy_via_prefect.py

# Deploy a specific branch
python scripts/deploy_via_prefect.py --branch feature-x

# Skip dependency install (code-only change)
python scripts/deploy_via_prefect.py --skip-deps

# Skip git push (already pushed)
python scripts/deploy_via_prefect.py --no-push

# Combine flags
python scripts/deploy_via_prefect.py --branch feature-x --skip-deps --no-push
```

### What It Does

1. Pushes the branch to origin (unless `--no-push`)
2. Finds the `deploy-superbot` Prefect deployment via API
3. Creates a flow run with the specified parameters
4. Polls the flow run status every 5 seconds until completion
5. Reports final status (COMPLETED or FAILED with message)

The flow on the VM then executes: git pull, uv pip install, systemctl restart, and health check (service status + log inspection).

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| "Deployment 'deploy-superbot' not found" | Flow not running on VM | SSH to VM and start it (see One-Time Setup above) |
| "Connection error" | No network access to Prefect server | Verify you can reach `136.111.85.127:4200` |
| Deploy FAILED with health check errors | Service crashed after restart | Check logs: `gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "sudo journalctl -u superbot -n 50 --no-pager"` |

## Verification Tests

After Step 9 shows clean startup, run these 8 tests in sequence.

### Test 1: Service Health

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "sudo systemctl is-active superbot"
```

Expected: `active`

### Test 2: Authorized @mention

In the designated Slack channel, send: `@SuperBot hello`

Expected within 3 seconds:
- Hourglass emoji reaction on your message
- "Working on it." thread reply
- Shortly after: "[Phase 1 -- agent not yet connected...]" in the thread

### Test 3: Unauthorized @mention

Have someone NOT in `ALLOWED_USERS` send `@SuperBot test` in the channel.

Expected: No response, no reaction. Bot appears offline to them.

### Test 4: Event Deduplication

Send the same @mention twice rapidly. Each message should get exactly one "Working on it." reply (not two replies on the same message).

### Test 5: /status Command

Run `/sb-status` in the channel.

Expected: Response showing "Idle", uptime, no current task.

### Test 6: /cancel Command

Run `/cancel` when bot is idle.

Expected: "Nothing is running."

### Test 7: /help Command

Run `/help` in the channel.

Expected: Message listing /sb-status, /cancel, /help with descriptions.

### Test 8: Log Check

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "sudo journalctl -u superbot --since='5 minutes ago' --no-pager"
```

Expected: Clean log entries, no authentication errors, no import errors.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| "SLACK_BOT_TOKEN not set" | `/home/bot/.env` not populated or `EnvironmentFile` path wrong in service | Re-run Step 4; check `systemd/superbot.service` EnvironmentFile path |
| Socket Mode connection refused | `SLACK_APP_TOKEN` is wrong or missing `connections:write` scope | Regenerate app-level token in Slack app settings with correct scope |
| Claude Code auth error | `claude login` was not run as `bot` user | SSH in, `sudo -u bot bash`, run `claude login` again |
| Startup script still running | VM just created | Check `/var/log/startup.log`; wait for "Bootstrap complete" |
| Bot does not respond to @mention | Bot not invited to channel, or channel ID wrong | Run `/invite @SuperBot` in the channel; verify `ALLOWED_CHANNEL` value |
| Bot responds but no emoji reaction | Missing `reactions:write` OAuth scope | Check Slack app OAuth scopes match `slack_manifest.yaml` |

## Phase 3: glab Setup

**When to run:** After Phase 1 deployment (bot user exists, `.env` populated with `GITLAB_TOKEN`).

The `glab` CLI enables Claude Code to create GitLab merge requests directly from the VM via its Bash tool. Without it, code-change tasks cannot complete the MR creation step.

### Steps

1. **Ensure `.env` contains required variables:**

   ```bash
   # On the VM, verify these are set in /home/bot/.env:
   GITLAB_TOKEN=glpat-YOUR-TOKEN
   GITLAB_REMOTE_URL=irismed/mic_transformer
   ```

2. **Copy the setup script to the VM:**

   ```bash
   gcloud compute scp scripts/setup_glab.sh bot@superbot-vm:/home/bot/scripts/setup_glab.sh --zone=us-west1-a
   ```

3. **Run the setup script as the bot user:**

   ```bash
   gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "sudo -u bot bash /home/bot/scripts/setup_glab.sh"
   ```

4. **Verify glab is installed and authenticated:**

   ```bash
   gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "sudo -u bot glab auth status"
   ```

   Expected: `Logged in to gitlab.com as <bot-user>`

5. **Verify MR access:**

   ```bash
   gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "sudo -u bot bash -c 'cd /home/bot/mic_transformer && glab mr list'"
   ```

   Expected: List of open MRs (or empty list), no authentication errors.

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `GITLAB_TOKEN is not set` | `.env` missing or variable not defined | Check `/home/bot/.env` contains `GITLAB_TOKEN=glpat-...` |
| packagecloud install fails | Network egress blocked | Verify Terraform firewall allows outbound HTTPS (port 443) |
| `glab auth login` fails | Token expired or invalid scopes | Regenerate GitLab PAT with `api` scope |
| `glab mr list` returns auth error | Token lacks repo access | Ensure PAT has `read_api` and `api` scopes for the target repo |

### Notes

- glab auth persists to `~/.config/glab-cli/` -- survives bot process restarts and VM reboots.
- The setup script is idempotent; re-running it will skip the install step if glab is already present.
- `GITLAB_REMOTE_URL` should be in `org/repo` format (e.g., `irismed/mic_transformer`).

## v1.1: Capability Parity Setup

**When to run:** After v1.0 is deployed and verified. These steps add Linear/Sentry MCP servers, multi-repo access, and custom skills.

### Prerequisites

- Linear API key (from Linear Settings > API > Personal API Keys)
- Sentry auth token (from Sentry Settings > Auth Tokens)
- GitLab PAT already configured (from Phase 1) with access to all 4 repos

### Step 1: Add v1.1 Environment Variables

Add these lines to `/home/bot/.env`:

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo -u bot bash -c '
    cat >> /home/bot/.env << \"ENV\"
LINEAR_API_KEY=lin_api_YOUR_KEY
SENTRY_AUTH_TOKEN=sntrys_YOUR_TOKEN
ADDITIONAL_REPOS=/home/bot/oso-fe-gsnap,/home/bot/irismed-service,/home/bot/oso-desktop
ENV
  '
"
```

### Step 2: Clone Additional Repositories

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo -u bot bash -c '
    source /home/bot/.env
    git clone \"https://oauth2:\${GITLAB_TOKEN}@gitlab.com/irismed/oso-fe-gsnap.git\" /home/bot/oso-fe-gsnap
    git clone \"https://oauth2:\${GITLAB_TOKEN}@gitlab.com/irismed/irismed-service.git\" /home/bot/irismed-service
    git clone \"https://oauth2:\${GITLAB_TOKEN}@gitlab.com/irismed/oso-desktop.git\" /home/bot/oso-desktop
  '
"
```

### Step 3: Deploy Custom Skills

Copy skill files to the bot user's Claude commands directory:

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo -u bot mkdir -p /home/bot/.claude/commands
"
gcloud compute scp skills/*.md bot@superbot-vm:/home/bot/.claude/commands/ --zone=us-west1-a
```

### Step 4: Pull Latest Code and Restart

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo -u bot bash -c 'cd /home/bot/super_bot && git pull origin main'
  sudo -u bot bash -c 'cd /home/bot/super_bot && source .venv/bin/activate && uv pip install -r requirements.txt'
  sudo systemctl restart superbot
  sudo systemctl status superbot
"
```

### Step 5: Verify MCP Servers

Check journal logs for MCP server connection:

```bash
gcloud compute ssh bot@superbot-vm --zone=us-west1-a -- "
  sudo journalctl -u superbot -n 50 --no-pager | grep -i 'mcp\|linear\|sentry\|add_dir'
"
```

Expected: `mcp_server_count=2`, `add_dir_count=3` in agent startup logs.

### Verification Tests

**Test 1 -- Linear query:**
```
@SuperBot what's the status on eyemed all location prep today?
```
Expected: Bot returns real Linear issue data (not calendar/location results).

**Test 2 -- Multi-repo query:**
```
@SuperBot what models does oso-fe-gsnap define for patient management?
```
Expected: Bot reads from `/home/bot/oso-fe-gsnap` and answers about the models.

**Test 3 -- Custom skill (if deployed):**
```
@SuperBot /audit-sync
```
Expected: Bot executes the skill and returns results.

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `mcp_server_count=0` in logs | `LINEAR_API_KEY` or `SENTRY_AUTH_TOKEN` empty in .env | Verify `/home/bot/.env` has non-empty values for both |
| `add_dirs.skip_missing` warnings | Repo not cloned yet | Run Step 2 to clone the repos |
| Linear MCP timeout on first use | npx downloading package | First query may be slow; subsequent queries use cached package |
| Sentry MCP auth error | Token expired or wrong org | Regenerate token in Sentry settings |

## v1.2: MCP Parity - Phase 5

**When to run:** After v1.1 is deployed and verified. This phase adds the mic-transformer MCP server, giving SuperBot direct access to mic_transformer tools (pipeline status, deployment, benefits fetch, etc.) via the Claude Agent SDK's native MCP wiring.

### Prerequisites

Before running the deploy script, verify these prerequisites:

1. **Config files copied to VM** -- The mic-transformer MCP server loads credentials from YAML config files. All 7 files must be present at `/home/bot/mic_transformer/config/`:

   - `config.yml`
   - `secrets.yml`
   - `gcs_utils_config.yml`
   - `db_irismedapp.yml`
   - `db_crystalpm_mirror.yml`
   - `clinic_gdrive_config.yml`
   - `clinic_gdrive_eyemed_config.yml`

   Copy from your local mic_transformer checkout:
   ```bash
   scp ~/mic_transformer/config/*.yml bot@VM_EXTERNAL_IP:/home/bot/mic_transformer/config/
   ```

   To find the VM external IP:
   ```bash
   gcloud compute instances describe superbot-vm --zone=us-west1-a --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
   ```

2. **Network access from VM to production server** -- Several MCP tools need to reach the production API at `136.111.85.127:8080`. The deploy script tests this in Step 5.

3. **mcp[cli]~=1.26.0 installed** -- The deploy script handles this in Step 1. The package provides `mcp.server.fastmcp.FastMCP` which the server imports.

### Deployment Steps

1. **Copy config files** (must be done before the deploy script):
   ```bash
   scp ~/mic_transformer/config/*.yml bot@VM_EXTERNAL_IP:/home/bot/mic_transformer/config/
   ```

2. **Run the deploy script:**
   ```bash
   bash scripts/deploy_v1.2_phase5.sh
   ```

   The script runs 8 steps: install MCP SDK, config file instructions, .env syntax audit, cold-start benchmark, network connectivity test, code pull + service restart, MCP registration check, and Slack verification instructions.

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Cold-start exceeds 60s | First import compiles .pyc files | SSH to VM, run the import command from Step 4 manually once to pre-compile, then restart |
| `mcp.mic_transformer_disabled_by_env` in logs | `MIC_TRANSFORMER_MCP_DISABLED=1` is set | Remove the line from `/home/bot/.env` and restart: `sudo systemctl restart superbot` |
| Missing config files errors in stderr | config/*.yml not copied to VM | SCP the files: `scp ~/mic_transformer/config/*.yml bot@VM_IP:/home/bot/mic_transformer/config/` |
| `mcp_server_count=0` but no disable log | mic_transformer path not found at `/home/bot/mic_transformer` | Verify the clone exists: `ls -la /home/bot/mic_transformer/.claude/mcp/mic-transformer/server.py` |
| .env syntax audit flags lines | `export` or `$VAR` interpolation in .env | Edit `/home/bot/.env` to use bare `KEY=VALUE` syntax (no `export`, no `${VAR}` references) |
| Network connectivity BLOCKED | VM firewall rules | Verify Terraform firewall allows outbound to `136.111.85.127:8080` |

**Disabling mic-transformer MCP for troubleshooting:**

Add this line to `/home/bot/.env` and restart the service:
```
MIC_TRANSFORMER_MCP_DISABLED=1
```

This cleanly disables the mic-transformer MCP server without affecting other MCP servers (Linear, Sentry). Check logs for confirmation:
```bash
sudo journalctl -u superbot -n 20 --no-pager | grep mic_transformer
```
Expected: `mcp.mic_transformer_disabled_by_env` log entry.

To re-enable, remove the line and restart:
```bash
sudo systemctl restart superbot
```

### Verification

Send this message in the SuperBot Slack channel:

```
@SuperBot check pipeline status for Beverly today
```

Expected: Bot responds in-thread with real pipeline status data from the mic-transformer MCP `check_pipeline_status` tool. If you see an error about missing tools or credentials, check the troubleshooting table above.

## v1.8: Production Ops

**When to run:** After v1.2 is deployed and verified. This release adds deploy-from-Slack commands, deploy status/preview, and an active-task guard so Nicole can deploy without SSH or gcloud.

### New Features

- **Deploy from Slack** -- type `deploy super_bot` or `deploy mic_transformer` directly in the Slack channel
- **Deploy status** -- see current commit, branch, and pending changes for both repos
- **Deploy preview** -- see which commits would be deployed before pulling the trigger
- **Active-task guard** -- deploy is blocked while an agent task is running (use `force` to override)

### Deploy Commands Reference

| Command | Description |
|---------|-------------|
| `deploy super_bot` | Deploy super_bot: pushes, pulls, restarts service, posts "I'm back" to thread |
| `deploy mic_transformer` | Deploy mic_transformer: triggers Prefect flow, polls until complete |
| `deploy status` | Shows current commit SHA, branch, and pending changes for both repos |
| `deploy preview super_bot` | Shows list of commits that would be deployed (or "nothing to deploy") |
| `deploy preview mic_transformer` | Shows list of commits that would be deployed for mic_transformer |
| `deploy force super_bot` | Deploy even if an agent task is currently running |
| `deploy force mic_transformer` | Deploy mic_transformer even if an agent task is running |

### Deployment

No additional VM setup needed. Deploy using the standard Prefect method:

```bash
python scripts/deploy_via_prefect.py
```

Or from Slack itself: `deploy super_bot`

### Verification Checklist

After deploying v1.8, verify these items in the Slack channel:

- [ ] **SDPL-01**: `deploy status` returns commit SHA, branch, and pending changes for both repos
- [ ] **SDPL-02**: `deploy preview super_bot` shows commit list or "nothing to deploy"
- [ ] **SDPL-03**: `deploy super_bot` posts pre-restart message with SHA details, restarts, posts "I'm back"
- [ ] **SDPL-04**: `deploy mic_transformer` triggers Prefect flow, shows polling progress, reports success/failure
- [ ] **SDPL-05**: `deploy force super_bot` works even when an agent task is running
- [ ] **VRFY-01**: Daily digest includes a changelog section
- [ ] **VRFY-02**: `crawl eyemed DME [date]` and `status on DME eyemed [date]` return fast-path responses
- [ ] **VRFY-03**: `crawl all sites for [date]` triggers batch crawl with background progress updates
- [ ] **VRFY-04**: Long agent tasks receive heartbeat edits on the progress message every few minutes

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| "deploy" command not recognized | Bot running old code without deploy handler | Redeploy via `python scripts/deploy_via_prefect.py` |
| Deploy blocked by active task | Agent task is running | Wait for task to finish or use `deploy force super_bot` |
| "I'm back" message never appears | Service failed to restart | Check logs: `sudo journalctl -u superbot -n 50 --no-pager` |
| mic_transformer deploy hangs | Prefect flow not served on VM | SSH to VM and start the flow: `cd /home/bot/super_bot && python prefect/deploy_superbot_flow.py` |
| Deploy preview shows no commits | Already up to date | Nothing to deploy; code on VM matches origin |
