#!/usr/bin/env bash
# Setup script for glab CLI on the GCP VM.
# Usage: chmod +x scripts/setup_glab.sh && bash scripts/setup_glab.sh
# Idempotent — safe to re-run.
set -euo pipefail

# ---------- Resolve paths ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------- Load .env ----------
if [[ ! -f "$BOT_ROOT/.env" ]]; then
  echo "ERROR: $BOT_ROOT/.env not found. Populate it first (see DEPLOY.md)."
  exit 1
fi
set -a
source "$BOT_ROOT/.env"
set +a

# ---------- Validate required vars ----------
if [[ -z "${GITLAB_TOKEN:-}" ]]; then
  echo "ERROR: GITLAB_TOKEN is not set in .env"
  exit 1
fi

# ---------- Install glab (idempotent) ----------
if command -v glab &>/dev/null; then
  echo "glab already installed: $(glab --version)"
else
  echo "Installing glab CLI..."
  curl -s https://packagecloud.io/install/repositories/gitlab/cli/script.deb.sh | sudo bash
  sudo apt install glab -y
  echo "Installed: $(glab --version)"
fi

# ---------- Authenticate ----------
echo "Authenticating glab against gitlab.com..."
glab auth login --token "$GITLAB_TOKEN" --hostname gitlab.com
echo "Auth complete."

# ---------- Verify ----------
echo ""
echo "=== Verification ==="
glab auth status

if [[ -n "${GITLAB_REMOTE_URL:-}" ]]; then
  echo ""
  echo "Testing MR list for $GITLAB_REMOTE_URL ..."
  glab mr list --repo "$GITLAB_REMOTE_URL"
  echo "MR list succeeded."
else
  echo ""
  echo "WARN: GITLAB_REMOTE_URL not set in .env — skipping MR list test."
  echo "Add GITLAB_REMOTE_URL=org/repo to .env for full verification."
fi

echo ""
echo "glab setup complete."
