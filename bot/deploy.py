"""
Deploy execution logic for super_bot (self-deploy) and mic_transformer (poll).

Triggered from handlers.py when the user sends a deploy command through the
agent pipeline.  Uses Prefect API to trigger deploys and deploy_state for
self-restart recovery.
"""

import asyncio
import time

import structlog

from bot import prefect_api
from bot.deploy_state import (
    get_deploy_preview,
    get_repo_status,
    record_deploy,
    write_deploy_state,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL = 5  # seconds between Prefect status checks
MAX_POLL_DURATION = 600  # 10 min max poll time for mic_transformer
TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "CRASHED"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _edit_progress(client, channel: str, ts: str, text: str) -> None:
    """Edit a Slack message in-place, swallowing errors."""
    try:
        await client.chat_update(channel=channel, ts=ts, text=text)
    except Exception:
        log.error("deploy.edit_progress_failed", channel=channel, ts=ts, exc_info=True)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def handle_deploy(
    repo_name: str,
    repo_config: dict,
    client,
    channel: str,
    thread_ts: str,
    user_id: str,
    ack_ts: str | None = None,
) -> None:
    """Execute a deploy for the given repo.

    Called from handlers.py after the deploy guard passes.  Edits the ack
    message in-place as each step completes.

    For super_bot (self_deploy=True): writes deploy-state, posts pre-restart
    message, triggers Prefect, then the process dies.  Post-restart recovery
    in app.py handles the "I'm back" message.

    For mic_transformer (self_deploy=False): triggers Prefect, polls for
    completion, and edits progress in-place.
    """
    msg_ts = ack_ts or thread_ts

    # ------------------------------------------------------------------
    # Step a: Check if already on latest
    # ------------------------------------------------------------------
    try:
        status = await get_repo_status(repo_name)
    except Exception as exc:
        await _edit_progress(
            client, channel, msg_ts,
            f"Failed to check repo status: {exc}",
        )
        return

    if status["behind"] == 0:
        await _edit_progress(
            client, channel, msg_ts,
            f"Already on latest (`{status['sha']}`). Nothing to deploy.",
        )
        return

    # ------------------------------------------------------------------
    # Step b: Dirty state warning
    # ------------------------------------------------------------------
    dirty_warning = ""
    if status["dirty"]:
        dirty_warning = "\n(uncommitted changes on VM -- proceeding anyway)"

    # ------------------------------------------------------------------
    # Step c: Deploy preview
    # ------------------------------------------------------------------
    try:
        preview_commits = await get_deploy_preview(repo_name)
    except Exception:
        preview_commits = "(could not fetch preview)"

    # ------------------------------------------------------------------
    # Step d: Find Prefect deployment
    # ------------------------------------------------------------------
    try:
        deployment_id = await prefect_api.find_deployment_id(
            repo_config["prefect_deployment"],
        )
    except Exception as exc:
        await _edit_progress(
            client, channel, msg_ts,
            f"Failed to contact Prefect: {exc}",
        )
        return

    if deployment_id is None:
        await _edit_progress(
            client, channel, msg_ts,
            f"Prefect deployment `{repo_config['prefect_deployment']}` not found.",
        )
        return

    # ------------------------------------------------------------------
    # Branch: self-deploy (super_bot) vs external deploy (mic_transformer)
    # ------------------------------------------------------------------

    if repo_config.get("self_deploy"):
        await _self_deploy(
            repo_name, repo_config, deployment_id,
            client, channel, thread_ts, msg_ts,
            user_id, status, dirty_warning, preview_commits,
        )
    else:
        await _external_deploy(
            repo_name, repo_config, deployment_id,
            client, channel, thread_ts, msg_ts,
            dirty_warning, preview_commits,
        )


# ---------------------------------------------------------------------------
# super_bot self-deploy
# ---------------------------------------------------------------------------


async def _self_deploy(
    repo_name: str,
    repo_config: dict,
    deployment_id: str,
    client,
    channel: str,
    thread_ts: str,
    msg_ts: str,
    user_id: str,
    status: dict,
    dirty_warning: str,
    preview_commits: str,
) -> None:
    """Self-deploy: write state, post message, trigger Prefect, die."""
    pre_sha = status["sha"]

    # Step f: Write deploy-state BEFORE triggering (source of truth)
    write_deploy_state(channel, thread_ts, pre_sha, user_id)

    # Step g: Pre-restart message
    pre_restart_msg = (
        f"Deploying {repo_name}...\n"
        f"`{pre_sha}` -> `origin/main`\n"
        f"```\n{preview_commits}\n```"
        f"{dirty_warning}\n\n"
        "Restarting now. I'll be back shortly.\n"
        "If I don't reply within 30 seconds, check logs: "
        "`sudo journalctl -u superbot -n 50`"
    )
    await _edit_progress(client, channel, msg_ts, pre_restart_msg)

    # Step h: Trigger Prefect (this will restart the bot process)
    try:
        run = await prefect_api.create_flow_run(
            deployment_id, {"branch": "main"},
        )
        log.info(
            "deploy.self_deploy_triggered",
            repo=repo_name,
            flow_run_id=run.get("id"),
            flow_run_name=run.get("name"),
        )
    except Exception as exc:
        log.error("deploy.self_deploy_trigger_failed", error=str(exc))
        await _edit_progress(
            client, channel, msg_ts,
            f"Failed to trigger Prefect deploy: {exc}",
        )

    # No polling -- the bot process will die when systemd restarts it.
    # Post-restart recovery in app.py handles the "I'm back" message.


# ---------------------------------------------------------------------------
# mic_transformer external deploy
# ---------------------------------------------------------------------------


async def _external_deploy(
    repo_name: str,
    repo_config: dict,
    deployment_id: str,
    client,
    channel: str,
    thread_ts: str,
    msg_ts: str,
    dirty_warning: str,
    preview_commits: str,
) -> None:
    """External deploy: trigger Prefect, poll, report."""

    # Step e: Trigger Prefect flow run
    try:
        run = await prefect_api.create_flow_run(
            deployment_id, {"branch": "main"},
        )
    except Exception as exc:
        await _edit_progress(
            client, channel, msg_ts,
            f"Failed to trigger Prefect deploy: {exc}",
        )
        return

    flow_run_id = run.get("id", "unknown")
    flow_run_name = run.get("name", "unknown")

    log.info(
        "deploy.external_deploy_triggered",
        repo=repo_name,
        flow_run_id=flow_run_id,
        flow_run_name=flow_run_name,
    )

    # Step f: Initial progress message
    await _edit_progress(
        client, channel, msg_ts,
        f"Deploying {repo_name}... triggered Prefect flow `{flow_run_name}`\n"
        f"```\n{preview_commits}\n```{dirty_warning}",
    )

    # Step g-j: Poll for completion
    start = time.monotonic()
    last_status = None

    while time.monotonic() - start < MAX_POLL_DURATION:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            run_data = await prefect_api.get_flow_run_status(flow_run_id)
        except Exception:
            log.warning("deploy.poll_error", flow_run_id=flow_run_id, exc_info=True)
            continue

        state = run_data.get("state", {})
        current_status = state.get("type", "UNKNOWN")

        # Edit on status change
        if current_status != last_status:
            last_status = current_status
            await _edit_progress(
                client, channel, msg_ts,
                f"Deploying {repo_name}... `{flow_run_name}` is {current_status.lower()}{dirty_warning}",
            )

        if current_status in TERMINAL_STATES:
            if current_status == "COMPLETED":
                # Record deploy timestamp
                try:
                    from bot.deploy_state import _git
                    new_sha = await _git(repo_config["dir"], "rev-parse", "--short", "HEAD")
                    record_deploy(repo_name, new_sha)
                except Exception:
                    pass
                await _edit_progress(
                    client, channel, msg_ts,
                    f"Deploy {repo_name} complete. "
                    f"Flow `{flow_run_name}` finished successfully.",
                )
            else:
                state_msg = state.get("message") or current_status
                await _edit_progress(
                    client, channel, msg_ts,
                    f"Deploy {repo_name} failed. "
                    f"Flow `{flow_run_name}`: {state_msg}",
                )
            return

    # Timeout
    await _edit_progress(
        client, channel, msg_ts,
        f"Deploy {repo_name} timed out after {MAX_POLL_DURATION // 60} minutes. "
        f"Flow `{flow_run_name}` may still be running -- check Prefect dashboard.",
    )
