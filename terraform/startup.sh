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

# 2. Install uv (fast Python package manager) — install system-wide
echo "[2/10] Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
cp /root/.local/bin/uv /usr/local/bin/uv
chmod 755 /usr/local/bin/uv

# 3. Install Node.js 20.x (required for Claude Code CLI)
echo "[3/10] Installing Node.js 20.x..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# 4. Create bot Linux user (no sudo, no login shell beyond bash)
echo "[4/10] Creating bot user..."
if ! id bot &>/dev/null; then
    useradd -m -s /bin/bash -c "SuperBot service user" bot
fi

# 5. Create venv and placeholder repo directory (clone deferred until credentials exist)
echo "[5/10] Setting up venv (repo clone deferred until .env is populated)..."
sudo -u bot bash << 'BOT'
    mkdir -p /home/bot/super_bot
BOT
# Clone is deferred — requires GITHUB_TOKEN from .env.
# After .env is populated, run:
#   source /home/bot/.env
#   sudo -u bot bash -c "git clone https://${GITHUB_TOKEN}@github.com/irismed-oso/super_bot.git /home/bot/super_bot"
#   sudo -u bot bash -c "cd /home/bot/super_bot && uv venv .venv && source .venv/bin/activate && uv pip install -r requirements.txt"

# 6. Create placeholder .env file for bot
echo "[6/10] Creating placeholder .env..."
sudo -u bot bash << 'BOTENV'
    cat > /home/bot/.env << 'ENV'
SLACK_BOT_TOKEN=REPLACE_ME
SLACK_APP_TOKEN=REPLACE_ME
GITHUB_TOKEN=REPLACE_ME
ALLOWED_USERS=REPLACE_ME
ALLOWED_CHANNEL=REPLACE_ME
ENV
    chmod 600 /home/bot/.env
BOTENV

# 7. Configure GitHub git credentials store as bot user
echo "[7/10] Configuring git credentials store..."
sudo -u bot bash << 'GITBOT'
    git config --global credential.helper store
    # Placeholder — operator populates GITHUB_TOKEN in .env, then runs:
    # echo "https://${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    # chmod 600 ~/.git-credentials
    touch /home/bot/.git-credentials
    chmod 600 /home/bot/.git-credentials
    chown bot:bot /home/bot/.git-credentials
GITBOT

# 8. Install Claude Code CLI (global, needs root for -g)
echo "[8/10] Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code
# After deploy: SSH as bot user and run 'claude login' interactively once

# 9. Systemd service (deferred — install after repo is cloned)
echo "[9/10] Systemd service install deferred until repo is cloned..."
# After cloning the repo, run:
#   cp /home/bot/super_bot/systemd/superbot.service /etc/systemd/system/
#   systemctl daemon-reload && systemctl enable superbot

# 10. Completion
echo "[10/10] Startup script complete."
echo "=== SuperBot VM startup finished at: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo ""
echo "NEXT STEPS:"
echo "  1. Populate /home/bot/.env with real values"
echo "  2. Run: echo 'https://\${GITHUB_TOKEN}@github.com' > /home/bot/.git-credentials && chmod 600 /home/bot/.git-credentials"
echo "  3. Clone repo: sudo -u bot git clone https://\${GITHUB_TOKEN}@github.com/irismed-oso/super_bot.git /home/bot/super_bot"
echo "  4. Setup venv: sudo -u bot bash -c 'cd /home/bot/super_bot && uv venv .venv && source .venv/bin/activate && uv pip install -r requirements.txt'"
echo "  5. Install service: cp /home/bot/super_bot/systemd/superbot.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable superbot"
echo "  6. SSH as bot user and run: claude login"
echo "  7. Start the service: systemctl start superbot"
