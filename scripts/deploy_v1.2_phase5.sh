#!/usr/bin/env bash
set -euo pipefail

# SuperBot v1.2 Phase 5 Deployment Script
# Run locally after: gcloud auth login
#
# Usage: bash scripts/deploy_v1.2_phase5.sh
#
# NOTE: Config files (config/*.yml) must be SCP'd separately to the VM
# because gcloud compute ssh does not support file transfers inline.
# See Step 2 for the required SCP command.

VM="superbot-vm"
ZONE="us-west1-a"
SSH="gcloud compute ssh bot@${VM} --zone=${ZONE} --"

echo "=== Step 1: Install mcp[cli] in mic_transformer venv ==="
$SSH "
  /home/bot/mic_transformer/.venv/bin/pip install 'mcp[cli]~=1.26.0'
  /home/bot/mic_transformer/.venv/bin/python -c \"from mcp.server.fastmcp import FastMCP; print('MCP SDK OK')\"
"

echo ""
echo "=== Step 2: Config file copy instructions ==="
echo ""
echo "The mic-transformer MCP server needs config files on the VM."
echo "Required files:"
echo "  - config.yml"
echo "  - secrets.yml"
echo "  - gcs_utils_config.yml"
echo "  - db_irismedapp.yml"
echo "  - db_crystalpm_mirror.yml"
echo "  - clinic_gdrive_config.yml"
echo "  - clinic_gdrive_eyemed_config.yml"
echo ""
echo "Run this command from your mic_transformer directory:"
echo "  scp config/*.yml bot@VM_EXTERNAL_IP:/home/bot/mic_transformer/config/"
echo ""
echo "To find the VM external IP:"
echo "  gcloud compute instances describe ${VM} --zone=${ZONE} --format='get(networkInterfaces[0].accessConfigs[0].natIP)'"
echo ""

echo "=== Step 3: Audit .env for systemd compatibility ==="
$SSH "
  echo 'Checking /home/bot/.env for systemd-incompatible syntax...'
  echo '--- Lines with export keyword ---'
  grep -nE '^export ' /home/bot/.env || echo '  (none found - OK)'
  echo '--- Lines with variable interpolation ---'
  grep -nE '\\\$[A-Z_]' /home/bot/.env || echo '  (none found - OK)'
  echo '--- Lines with backticks ---'
  grep -nE '\`' /home/bot/.env || echo '  (none found - OK)'
  echo 'Audit complete.'
"

echo ""
echo "=== Step 4: Benchmark MCP cold-start ==="
$SSH "
  echo 'Measuring mic-transformer MCP server import time...'
  time /home/bot/mic_transformer/.venv/bin/python -c \"
import sys, os
sys.path.insert(0, '/home/bot/mic_transformer')
sys.path.insert(0, '/home/bot/mic_transformer/lib')
os.chdir('/home/bot/mic_transformer')
from mcp.server.fastmcp import FastMCP
from tools import analytics, azure_mirror, benefits, crawler, deploy, extraction, gdrive, ingestion, ivt_ingestion, posting, reduction, status, storage
print('All modules imported successfully')
\"
  echo ''
  echo 'Guidance:'
  echo '  < 30s : Good - no action needed'
  echo '  30-60s: Consider pre-warming strategy'
  echo '  > 60s : MUST implement pre-warming (SDK timeout is 60s)'
"

echo ""
echo "=== Step 5: Test network connectivity ==="
$SSH "
  echo 'Testing connectivity to production API...'
  HTTP_CODE=\$(curl -s -o /dev/null -w '%{http_code}' http://136.111.85.127:8080/version || echo 'BLOCKED')
  echo \"Response code: \${HTTP_CODE}\"
  if [ \"\${HTTP_CODE}\" = 'BLOCKED' ]; then
    echo 'WARNING: Cannot reach production API from VM'
  elif [ \"\${HTTP_CODE}\" = '200' ]; then
    echo 'OK - production API reachable'
  else
    echo \"Unexpected response code: \${HTTP_CODE}\"
  fi
"

echo ""
echo "=== Step 6: Pull latest super_bot code and restart ==="
$SSH "
  sudo -u bot bash -c 'cd /home/bot/super_bot && git pull origin main'
  sudo -u bot bash -c 'cd /home/bot/super_bot && source .venv/bin/activate && uv pip install -r requirements.txt'
  sudo systemctl restart superbot
  sleep 3
  sudo systemctl status superbot --no-pager
"

echo ""
echo "=== Step 7: Check MCP server registration in logs ==="
$SSH "
  echo 'Looking for MCP registration entries...'
  sudo journalctl -u superbot -n 50 --no-pager | grep -E 'mcp_server_count|mic.transformer|mic_transformer' || echo 'No MCP log entries yet (will appear on first task)'
"

echo ""
echo "=== Step 8: Slack verification ==="
echo ""
echo "Deployment complete. Send this message in Slack to verify mic-transformer MCP:"
echo ""
echo "  @SuperBot check pipeline status for Beverly today"
echo ""
echo "Expected: Bot should use mic-transformer MCP tools to check pipeline status."
