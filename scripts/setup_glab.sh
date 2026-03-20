#!/usr/bin/env bash
# Setup script for gh (GitHub CLI) on the GCP VM.
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
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN is not set in .env"
  exit 1
fi

# ---------- Install gh (idempotent) ----------
if command -v gh &>/dev/null; then
  echo "gh already installed: $(gh --version | head -1)"
else
  echo "Installing GitHub CLI..."
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
  sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
  sudo apt update -qq
  sudo apt install gh -y
  echo "Installed: $(gh --version | head -1)"
fi

# ---------- Authenticate ----------
echo "Authenticating gh with GITHUB_TOKEN..."
echo "$GITHUB_TOKEN" | gh auth login --with-token
echo "Auth complete."

# ---------- Verify ----------
echo ""
echo "=== Verification ==="
gh auth status

if [[ -n "${GITHUB_REMOTE_URL:-}" ]]; then
  echo ""
  echo "Testing PR list for $GITHUB_REMOTE_URL ..."
  gh pr list --repo "$GITHUB_REMOTE_URL"
  echo "PR list succeeded."
else
  echo ""
  echo "WARN: GITHUB_REMOTE_URL not set in .env — skipping PR list test."
  echo "Add GITHUB_REMOTE_URL=org/repo to .env for full verification."
fi

echo ""
echo "gh setup complete."
