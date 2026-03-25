#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# SuperBot Deploy Script
# Pushes code, SSHs to VM, pulls, installs deps, restarts, verifies health.
# Run locally after: gcloud auth login
#
# Usage: bash scripts/deploy.sh [OPTIONS]
# ---------------------------------------------------------------------------

VM="superbot-vm"
ZONE="us-west1-a"
BOT_USER="bot"
SERVICE="superbot"
REPO_DIR="/home/bot/super_bot"

# Defaults
BRANCH=""
SKIP_PUSH=false
SKIP_DEPS=false

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: bash scripts/deploy.sh [OPTIONS]

Deploy the current branch to the SuperBot VM.

Options:
  --branch BRANCH   Deploy a specific branch (default: current branch)
  --skip-push       Skip the git push step (useful when already pushed)
  --skip-deps       Skip pip install step (for code-only changes)
  --help            Show this help message

Examples:
  bash scripts/deploy.sh                     # push + full deploy
  bash scripts/deploy.sh --skip-deps         # push + deploy without pip install
  bash scripts/deploy.sh --skip-push         # deploy only (already pushed)
  bash scripts/deploy.sh --branch feature-x  # deploy a specific branch
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --skip-push)
            SKIP_PUSH=true
            shift
            ;;
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Resolve branch
if [[ -z "$BRANCH" ]]; then
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
fi

echo "======================================"
echo "  SuperBot Deploy"
echo "  Branch: $BRANCH"
echo "  VM:     $VM ($ZONE)"
echo "======================================"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Push to origin
# ---------------------------------------------------------------------------
if [[ "$SKIP_PUSH" == false ]]; then
    echo "=== Step 1: Push $BRANCH to origin ==="
    git push origin "$BRANCH"
    echo ""
else
    echo "=== Step 1: Push (skipped) ==="
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 2: SSH to VM and pull latest code
# ---------------------------------------------------------------------------
echo "=== Step 2: Pull latest code on VM ==="
gcloud compute ssh "$BOT_USER@$VM" --zone="$ZONE" -- \
    "sudo -u $BOT_USER bash -c 'cd $REPO_DIR && git pull origin $BRANCH'"
echo ""

# ---------------------------------------------------------------------------
# Step 3: Install Python dependencies
# ---------------------------------------------------------------------------
if [[ "$SKIP_DEPS" == false ]]; then
    echo "=== Step 3: Install dependencies ==="
    gcloud compute ssh "$BOT_USER@$VM" --zone="$ZONE" -- \
        "sudo -u $BOT_USER bash -c 'cd $REPO_DIR && source .venv/bin/activate && uv pip install -r requirements.txt'"
    echo ""
else
    echo "=== Step 3: Install dependencies (skipped) ==="
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 4: Restart systemd service
# ---------------------------------------------------------------------------
echo "=== Step 4: Restart $SERVICE ==="
gcloud compute ssh "$BOT_USER@$VM" --zone="$ZONE" -- \
    "sudo systemctl restart $SERVICE"
echo "Waiting for service to start..."
sleep 3
echo ""

# ---------------------------------------------------------------------------
# Step 5: Health check
# ---------------------------------------------------------------------------
echo "=== Step 5: Health check ==="

# Check if service is active
STATUS=$(gcloud compute ssh "$BOT_USER@$VM" --zone="$ZONE" -- \
    "sudo systemctl is-active $SERVICE" 2>/dev/null || true)

# Check recent logs for crash indicators
CRASH_LINES=$(gcloud compute ssh "$BOT_USER@$VM" --zone="$ZONE" -- \
    "sudo journalctl -u $SERVICE -n 20 --no-pager" 2>/dev/null || true)

CRASH_DETECTED=false
if echo "$CRASH_LINES" | grep -qiE "ERROR|Traceback"; then
    CRASH_DETECTED=true
fi

# Print service status
echo ""
echo "--- Service Status ---"
gcloud compute ssh "$BOT_USER@$VM" --zone="$ZONE" -- \
    "sudo systemctl status $SERVICE --no-pager" 2>/dev/null || true

echo ""
echo "--- Recent Logs (last 20 lines) ---"
echo "$CRASH_LINES"

# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------
echo ""
echo "======================================"
if [[ "$STATUS" == "active" && "$CRASH_DETECTED" == false ]]; then
    echo "  DEPLOY SUCCESS"
    echo "  Service: $STATUS"
    echo "  Branch:  $BRANCH"
    echo "======================================"
    echo ""
    echo "Next: Send '@SuperBot hello' in Slack to verify."
    exit 0
else
    echo "  DEPLOY FAILED"
    echo "  Service: $STATUS"
    if [[ "$CRASH_DETECTED" == true ]]; then
        echo "  Crash indicators found in logs"
    fi
    echo "======================================"
    echo ""
    echo "Check logs: gcloud compute ssh $BOT_USER@$VM --zone=$ZONE -- 'sudo journalctl -u $SERVICE -n 50 --no-pager'"
    exit 1
fi
