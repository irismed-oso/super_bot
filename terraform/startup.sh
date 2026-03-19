#!/usr/bin/env bash
set -euo pipefail

# Redirect all output to log file
exec > >(tee -a /var/log/startup.log) 2>&1

echo "=== SuperBot VM startup script ==="
echo "Started at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1. System packages
echo "[1/10] Installing system packages..."
apt-get update -qq
apt-get install -y -qq git python3 python3-pip curl

# 2. Install uv (fast Python package manager)
echo "[2/10] Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.cargo/bin:$PATH"

# 3. Install Node.js 20.x (required for Claude Code CLI)
echo "[3/10] Installing Node.js 20.x..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# 4. Create bot Linux user (no sudo, no login shell beyond bash)
echo "[4/10] Creating bot user..."
if ! id bot &>/dev/null; then
    useradd -m -s /bin/bash -c "SuperBot service user" bot
fi

# 5. Clone super_bot repo and set up venv as bot user
echo "[5/10] Cloning repo and setting up venv..."
sudo -u bot bash << 'BOT'
    cd /home/bot
    git clone https://gitlab.com/irismed/super_bot.git super_bot
    /root/.cargo/bin/uv venv /home/bot/super_bot/.venv
    source /home/bot/super_bot/.venv/bin/activate
    /root/.cargo/bin/uv pip install -r /home/bot/super_bot/requirements.txt
BOT
# NOTE: mic_transformer clone is deferred — requires GITLAB_TOKEN from .env
# which the operator populates manually. After .env is populated, run:
#   sudo -u bot bash -c 'cd /home/bot && git clone https://oauth2:${GITLAB_TOKEN}@gitlab.com/irismed/mic_transformer.git'

# 6. Create placeholder .env file for bot
echo "[6/10] Creating placeholder .env..."
sudo -u bot bash << 'BOTENV'
    cat > /home/bot/.env << 'ENV'
SLACK_BOT_TOKEN=REPLACE_ME
SLACK_APP_TOKEN=REPLACE_ME
GITLAB_TOKEN=REPLACE_ME
ALLOWED_USERS=REPLACE_ME
ALLOWED_CHANNEL=REPLACE_ME
ENV
    chmod 600 /home/bot/.env
BOTENV

# 7. Configure GitLab git credentials store as bot user
echo "[7/10] Configuring git credentials store..."
sudo -u bot bash << 'GITBOT'
    git config --global credential.helper store
    # Placeholder — operator populates GITLAB_TOKEN in .env, then runs:
    # echo "https://oauth2:${GITLAB_TOKEN}@gitlab.com" > ~/.git-credentials
    # chmod 600 ~/.git-credentials
    touch /home/bot/.git-credentials
    chmod 600 /home/bot/.git-credentials
    chown bot:bot /home/bot/.git-credentials
GITBOT

# 8. Install Claude Code CLI as bot user
echo "[8/10] Installing Claude Code CLI..."
sudo -u bot bash -c 'npm install -g @anthropic-ai/claude-code'
# After deploy: SSH as bot user and run 'claude login' interactively once

# 9. Install systemd service (do NOT start yet)
echo "[9/10] Installing systemd service..."
cp /home/bot/super_bot/systemd/superbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable superbot
# Do NOT start: systemctl start superbot
# Start after .env is populated — see DEPLOY.md

# 10. Completion
echo "[10/10] Startup script complete."
echo "=== SuperBot VM startup finished at: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo ""
echo "NEXT STEPS:"
echo "  1. Populate /home/bot/.env with real values"
echo "  2. Run: echo 'https://oauth2:\${GITLAB_TOKEN}@gitlab.com' > /home/bot/.git-credentials"
echo "  3. SSH as bot user and run: claude login"
echo "  4. Start the service: systemctl start superbot"
