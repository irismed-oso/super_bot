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
