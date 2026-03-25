---
phase: quick
plan: 2
type: execute
wave: 1
depends_on: []
files_modified:
  - prefect/deploy_superbot_flow.py
  - scripts/deploy_via_prefect.py
autonomous: true
must_haves:
  truths:
    - "User can deploy SuperBot from local machine without gcloud auth"
    - "Deploy triggers git pull, dependency install, and service restart on VM"
    - "Deploy reports success/failure status back to caller"
  artifacts:
    - path: "prefect/deploy_superbot_flow.py"
      provides: "Prefect flow that runs deploy steps locally on the VM"
    - path: "scripts/deploy_via_prefect.py"
      provides: "Local script to trigger deploy via Prefect API"
  key_links:
    - from: "scripts/deploy_via_prefect.py"
      to: "Prefect API at 136.111.85.127:4200"
      via: "HTTP POST to create flow run"
      pattern: "deployments.*create_flow_run"
---

<objective>
Create a Prefect-based deploy pipeline for SuperBot so deployments can be triggered
via the Prefect API instead of requiring `gcloud auth login` + SSH.

Purpose: The current `scripts/deploy.sh` requires `gcloud compute ssh` which needs
active gcloud auth. This expires and blocks deploys. Since the Prefect server at
136.111.85.127:4200 is already accessible (used by bot/prefect_api.py), we can
create a Prefect flow on the VM that does the deploy, and trigger it remotely.

Output: A Prefect flow file to deploy on the VM, and a local trigger script.
</objective>

<execution_context>
@/Users/hanjing/.claude/get-shit-done/workflows/execute-plan.md
@/Users/hanjing/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@scripts/deploy.sh (current deploy script -- replicate this logic in the Prefect flow)
@bot/prefect_api.py (existing Prefect API client -- reuse patterns for auth/URL)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create Prefect deploy flow for VM</name>
  <files>prefect/deploy_superbot_flow.py</files>
  <action>
Create `prefect/deploy_superbot_flow.py` -- a Prefect flow that runs ON the VM
(where the Prefect worker executes it). The flow should:

1. Accept parameters: `branch` (str, default "main"), `skip_deps` (bool, default False)
2. Define tasks (Prefect tasks, not to be confused with plan tasks):
   - `git_pull`: runs `git -C /home/bot/super_bot pull origin {branch}` via subprocess
   - `install_deps`: runs `cd /home/bot/super_bot && source .venv/bin/activate && uv pip install -r requirements.txt` (skipped if skip_deps=True)
   - `restart_service`: runs `sudo systemctl restart superbot` via subprocess
   - `health_check`: waits 3 seconds, then checks `sudo systemctl is-active superbot` and `sudo journalctl -u superbot -n 20 --no-pager` for ERROR/Traceback. Returns pass/fail with log snippet.
3. The flow should return a dict with: `{"status": "success"|"failed", "branch": branch, "logs": str}`
4. At the bottom, include a `if __name__ == "__main__"` block that registers this as
   a Prefect deployment named "deploy-superbot" using `flow.serve(name="deploy-superbot")`
   so it can be triggered via API. Use Prefect 2.x API patterns (import from prefect).
5. Use `subprocess.run` with `capture_output=True, text=True, check=True` for shell commands.
   For commands needing bash (source activate), use `shell=True`.
6. Include clear docstrings explaining this runs on the VM, not locally.

Note: Prefect is already installed on the VM (the Prefect worker runs there).
The bot user can run git and pip. `sudo systemctl` works because the bot user
has passwordless sudo for systemctl (already configured for restart_superbot.sh).
  </action>
  <verify>python -c "import ast; ast.parse(open('prefect/deploy_superbot_flow.py').read()); print('syntax ok')"</verify>
  <done>Prefect flow file exists with git_pull, install_deps, restart_service, health_check tasks and a serve() entrypoint</done>
</task>

<task type="auto">
  <name>Task 2: Create local trigger script</name>
  <files>scripts/deploy_via_prefect.py</files>
  <action>
Create `scripts/deploy_via_prefect.py` -- a standalone Python script that triggers
the deploy-superbot Prefect deployment from any machine (no gcloud needed).

1. Use httpx (already in requirements.txt... actually it's not, so use `requests` or
   better yet use `urllib.request` from stdlib to avoid any dependency).
   Actually, use `httpx` since the bot uses it. If the user runs this from the super_bot
   venv, httpx is available. Add a try/except import that falls back to urllib if needed.
2. Reuse the same Prefect API URL and auth from bot/prefect_api.py:
   - PREFECT_API = "http://136.111.85.127:4200/api"
   - PREFECT_AUTH = ("shen", "tofu")
3. Script flow:
   a. Parse CLI args: `--branch` (default "main"), `--skip-deps` flag
   b. First, push current branch to origin (subprocess git push)
   c. Find deployment ID by name "deploy-superbot" via POST /deployments/filter
   d. Create flow run via POST /deployments/{id}/create_flow_run with parameters
   e. Print the flow run ID and name
   f. Poll GET /flow_runs/{id} every 5 seconds until terminal state
      (COMPLETED, FAILED, CRASHED, CANCELLED)
   g. Print final status and any state message
4. Use argparse for CLI. Make it a proper script with `if __name__ == "__main__"`.
5. Use only stdlib `urllib.request` + `json` for HTTP to avoid dependency issues
   when running outside the venv. Use basic auth via urllib.request.Request headers
   (base64 encode "shen:tofu").
6. Print clear output: "Triggering deploy...", "Flow run: {name} ({id})",
   "Polling... state: RUNNING", "Deploy COMPLETED" or "Deploy FAILED: {message}"
  </action>
  <verify>python scripts/deploy_via_prefect.py --help</verify>
  <done>Script prints usage with --branch and --skip-deps options. Can be run from any machine with Python 3.10+ and network access to the Prefect server.</done>
</task>

<task type="auto">
  <name>Task 3: Update DEPLOY.md with Prefect deploy instructions</name>
  <files>DEPLOY.md</files>
  <action>
Add a new section to DEPLOY.md (after the "Routine Deployments" section) titled
"## Deploy via Prefect (No gcloud auth needed)".

Content:
1. Explain this method triggers a Prefect flow on the VM -- no SSH or gcloud auth required.
2. Prerequisites: Network access to 136.111.85.127:4200, Python 3.10+
3. One-time setup on VM: `cd /home/bot/super_bot && python prefect/deploy_superbot_flow.py`
   (this registers the deployment with Prefect and keeps it running as a served flow)
4. Usage: `python scripts/deploy_via_prefect.py` (deploys main) or
   `python scripts/deploy_via_prefect.py --branch feature-x --skip-deps`
5. Mention that the flow does the same steps as `scripts/deploy.sh`: push, pull, install deps, restart, health check.
6. Note: The Prefect flow must be running on the VM (via the serve() call or a Prefect work pool).
   If it's not running, you need SSH access once to start it.
  </action>
  <verify>grep -q "Deploy via Prefect" DEPLOY.md</verify>
  <done>DEPLOY.md contains Prefect deploy instructions with prerequisites, setup, and usage</done>
</task>

</tasks>

<verification>
1. `python -c "import ast; ast.parse(open('prefect/deploy_superbot_flow.py').read())"` -- flow parses
2. `python scripts/deploy_via_prefect.py --help` -- trigger script works
3. `grep "Deploy via Prefect" DEPLOY.md` -- docs updated
</verification>

<success_criteria>
- Prefect flow file exists that can run deploy steps on the VM
- Local trigger script exists that hits the Prefect API to start a deploy
- No gcloud auth dependency in the new deploy path
- DEPLOY.md documents the new approach
</success_criteria>

<output>
After completion, create `.planning/quick/2-create-way-to-deploy-super-bot-productio/2-SUMMARY.md`
</output>
