"""
Prefect flow that deploys SuperBot on the VM.

This file runs ON the VM where the Prefect worker executes it -- not locally.
It performs: git pull, dependency install, service restart, and health check.

One-time setup (on VM):
    cd /home/bot/super_bot
    python prefect/deploy_superbot_flow.py

This registers the "deploy-superbot" deployment with the Prefect server and
keeps the flow available for remote triggering via the Prefect API.
"""

import subprocess
import time

from prefect import flow, get_run_logger, task

REPO_DIR = "/home/bot/super_bot"
SERVICE = "superbot"


@task(name="git-pull")
def git_pull(branch: str) -> str:
    """Pull the latest code from origin for the given branch."""
    logger = get_run_logger()
    logger.info(f"Pulling branch '{branch}' in {REPO_DIR}")
    result = subprocess.run(
        ["git", "-C", REPO_DIR, "pull", "origin", branch],
        capture_output=True,
        text=True,
        check=True,
    )
    logger.info(result.stdout)
    return result.stdout


@task(name="install-deps")
def install_deps() -> str:
    """Install Python dependencies via uv pip install."""
    logger = get_run_logger()
    logger.info("Installing dependencies")
    result = subprocess.run(
        f"cd {REPO_DIR} && source .venv/bin/activate && uv pip install -r requirements.txt",
        capture_output=True,
        text=True,
        check=True,
        shell=True,
    )
    logger.info(result.stdout)
    return result.stdout


@task(name="restart-service")
def restart_service() -> str:
    """Restart the superbot systemd service."""
    logger = get_run_logger()
    logger.info(f"Restarting {SERVICE}")
    result = subprocess.run(
        ["sudo", "systemctl", "restart", SERVICE],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@task(name="health-check")
def health_check() -> dict:
    """Wait 3 seconds, then check service status and logs for errors.

    Returns a dict with 'healthy' (bool) and 'log_snippet' (str).
    """
    logger = get_run_logger()
    logger.info("Waiting 3 seconds for service to start...")
    time.sleep(3)

    # Check if service is active
    status_result = subprocess.run(
        ["sudo", "systemctl", "is-active", SERVICE],
        capture_output=True,
        text=True,
    )
    is_active = status_result.stdout.strip() == "active"

    # Check recent logs for crash indicators
    log_result = subprocess.run(
        ["sudo", "journalctl", "-u", SERVICE, "-n", "20", "--no-pager"],
        capture_output=True,
        text=True,
    )
    log_snippet = log_result.stdout
    has_errors = any(
        indicator in log_snippet for indicator in ["ERROR", "Traceback"]
    )

    healthy = is_active and not has_errors
    logger.info(f"Service active: {is_active}, errors in logs: {has_errors}")

    return {"healthy": healthy, "log_snippet": log_snippet}


@flow(name="deploy-superbot")
def deploy_superbot(branch: str = "main", skip_deps: bool = False) -> dict:
    """Deploy SuperBot on the VM.

    This flow runs ON the VM (via the Prefect worker). It pulls the latest
    code, optionally installs dependencies, restarts the systemd service,
    and runs a health check.

    Args:
        branch: Git branch to deploy (default: "main").
        skip_deps: If True, skip pip install step.

    Returns:
        Dict with status ("success" or "failed"), branch, and logs.
    """
    logger = get_run_logger()
    logs = []

    try:
        # Step 1: Pull latest code
        pull_output = git_pull(branch)
        logs.append(f"=== Git Pull ===\n{pull_output}")

        # Step 2: Install dependencies (unless skipped)
        if skip_deps:
            logger.info("Skipping dependency install (skip_deps=True)")
            logs.append("=== Dependencies ===\nSkipped")
        else:
            deps_output = install_deps()
            logs.append(f"=== Dependencies ===\n{deps_output}")

        # Step 3: Restart service
        restart_service()
        logs.append("=== Restart ===\nService restarted")

        # Step 4: Health check
        health = health_check()
        logs.append(f"=== Health Check ===\n{health['log_snippet']}")

        if health["healthy"]:
            logger.info("Deploy SUCCESS")
            return {
                "status": "success",
                "branch": branch,
                "logs": "\n".join(logs),
            }
        else:
            logger.error("Deploy FAILED: health check failed")
            return {
                "status": "failed",
                "branch": branch,
                "logs": "\n".join(logs),
            }

    except subprocess.CalledProcessError as e:
        logger.error(f"Deploy FAILED: {e}")
        logs.append(f"=== Error ===\n{e.stderr or e.stdout or str(e)}")
        return {
            "status": "failed",
            "branch": branch,
            "logs": "\n".join(logs),
        }


if __name__ == "__main__":
    deploy_superbot.serve(name="deploy-superbot")
