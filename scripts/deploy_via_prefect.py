#!/usr/bin/env python3
"""
Trigger a SuperBot deploy via the Prefect API.

No gcloud auth or SSH required -- just network access to the Prefect server.
Uses only Python stdlib (urllib, json, base64) so it works without a venv.

Usage:
    python scripts/deploy_via_prefect.py                    # deploy main
    python scripts/deploy_via_prefect.py --branch feature-x # deploy a branch
    python scripts/deploy_via_prefect.py --skip-deps        # skip pip install
"""

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

PREFECT_API = "http://136.111.85.127:4200/api"
PREFECT_USER = "shen"
PREFECT_PASS = "tofu"
DEPLOYMENT_NAME = "deploy-superbot"
POLL_INTERVAL = 5  # seconds

TERMINAL_STATES = {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"}


def _auth_header() -> str:
    """Build Basic auth header value."""
    creds = base64.b64encode(f"{PREFECT_USER}:{PREFECT_PASS}".encode()).decode()
    return f"Basic {creds}"


def _api_request(method: str, path: str, data: dict | None = None) -> dict:
    """Make an authenticated request to the Prefect API."""
    url = f"{PREFECT_API}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {body_text}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        print(f"Is the Prefect server reachable at {PREFECT_API}?", file=sys.stderr)
        sys.exit(1)


def find_deployment_id() -> str:
    """Look up the deploy-superbot deployment by name."""
    results = _api_request(
        "POST",
        "/deployments/filter",
        {"deployments": {"name": {"any_": [DEPLOYMENT_NAME]}}},
    )
    if not results:
        print(f"Deployment '{DEPLOYMENT_NAME}' not found.", file=sys.stderr)
        print(
            "Has the flow been started on the VM?  "
            "Run: cd /home/bot/super_bot && python prefect/deploy_superbot_flow.py",
            file=sys.stderr,
        )
        sys.exit(1)
    return results[0]["id"]


def create_flow_run(deployment_id: str, branch: str, skip_deps: bool) -> dict:
    """Create a flow run for the deployment."""
    return _api_request(
        "POST",
        f"/deployments/{deployment_id}/create_flow_run",
        {"parameters": {"branch": branch, "skip_deps": skip_deps}},
    )


def poll_flow_run(flow_run_id: str) -> dict:
    """Poll until the flow run reaches a terminal state."""
    while True:
        run = _api_request("GET", f"/flow_runs/{flow_run_id}")
        state_type = run.get("state", {}).get("type", "UNKNOWN")
        print(f"  Polling... state: {state_type}")
        if state_type in TERMINAL_STATES:
            return run
        time.sleep(POLL_INTERVAL)


def git_push(branch: str) -> None:
    """Push the current branch to origin."""
    print(f"Pushing {branch} to origin...")
    result = subprocess.run(
        ["git", "push", "origin", branch],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Non-fatal: maybe already pushed or no upstream
        print(f"  Warning: git push returned {result.returncode}")
        if result.stderr:
            print(f"  {result.stderr.strip()}")
    else:
        print("  Push complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy SuperBot via Prefect (no gcloud auth needed).",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch to deploy (default: main)",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip pip install step on the VM",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip git push before triggering deploy",
    )
    args = parser.parse_args()

    print("======================================")
    print("  SuperBot Deploy (via Prefect)")
    print(f"  Branch: {args.branch}")
    print("======================================")
    print()

    # Step 1: Push to origin
    if not args.no_push:
        git_push(args.branch)
        print()

    # Step 2: Find deployment
    print(f"Finding deployment '{DEPLOYMENT_NAME}'...")
    deployment_id = find_deployment_id()
    print(f"  Deployment ID: {deployment_id}")
    print()

    # Step 3: Trigger flow run
    print("Triggering deploy...")
    run = create_flow_run(deployment_id, args.branch, args.skip_deps)
    flow_run_id = run.get("id", "unknown")
    flow_run_name = run.get("name", "unknown")
    print(f"  Flow run: {flow_run_name} ({flow_run_id})")
    print()

    # Step 4: Poll until complete
    print("Waiting for deploy to finish...")
    final = poll_flow_run(flow_run_id)
    state = final.get("state", {})
    state_type = state.get("type", "UNKNOWN")
    state_msg = state.get("message", "")

    print()
    print("======================================")
    if state_type == "COMPLETED":
        print(f"  Deploy COMPLETED")
    else:
        print(f"  Deploy {state_type}")
        if state_msg:
            print(f"  Message: {state_msg}")
    print(f"  Branch: {args.branch}")
    print("======================================")

    sys.exit(0 if state_type == "COMPLETED" else 1)


if __name__ == "__main__":
    main()
