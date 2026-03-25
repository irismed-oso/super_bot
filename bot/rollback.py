"""
Rollback execution logic for super_bot (self-rollback) and mic_transformer (poll).

Triggered from handlers.py when the user sends a rollback command.  Uses Prefect
API to trigger deploys to a target SHA and deploy_state for self-restart recovery.

Automatic roll-forward: if a rollback fails health check, the bot deploys back to
the pre-rollback SHA.  If roll-forward also fails, it reports that manual SSH
intervention is needed.
"""

import asyncio
import time

import structlog

from bot import prefect_api
from bot.deploy_state import (
    _git,
    get_last_deploy,
    record_deploy,
    write_deploy_state,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants (same as deploy.py)
# ---------------------------------------------------------------------------

POLL_INTERVAL = 5  # seconds between Prefect status checks
MAX_POLL_DURATION = 600  # 10 min max poll time
TERMINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "CRASHED"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _edit_progress(client, channel: str, ts: str, text: str) -> None:
    """Edit a Slack message in-place, swallowing errors."""
    try:
        await client.chat_update(channel=channel, ts=ts, text=text)
    except Exception:
        log.error("rollback.edit_progress_failed", channel=channel, ts=ts, exc_info=True)


async def _health_check(repo_name: str, repo_config: dict) -> tuple[bool, str]:
    """Check whether a repo is healthy after rollback.

    For repos with a ``service`` key: runs ``systemctl is-active`` and scans
    last 10 journal lines for error/traceback indicators.

    For repos without a service (e.g. mic_transformer with service=None):
    the Prefect COMPLETED state is sufficient -- returns (True, "").
    """
    service = repo_config.get("service")
    if not service:
        return (True, "")

    try:
        # Check service is active
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", service,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        status = stdout.decode().strip()
        if status != "active":
            return (False, f"Service {service} is {status}")

        # Check journal for recent errors
        proc2 = await asyncio.create_subprocess_exec(
            "journalctl", "-u", service, "-n", "10", "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await proc2.communicate()
        journal = stdout2.decode().lower()
        for indicator in ("error", "traceback"):
            if indicator in journal:
                return (False, f"Found '{indicator}' in recent {service} journal logs")

        return (True, "")
    except Exception as exc:
        return (False, f"Health check error: {exc}")


async def _trigger_and_poll(
    deployment_id: str, branch_sha: str, client, channel: str, msg_ts: str,
    repo_name: str, label: str,
) -> str | None:
    """Trigger a Prefect deploy and poll until terminal state.

    Returns the terminal state string (e.g. "COMPLETED") or None on timeout.
    """
    try:
        run = await prefect_api.create_flow_run(deployment_id, {"branch": branch_sha})
    except Exception as exc:
        await _edit_progress(client, channel, msg_ts, f"{label} failed to trigger Prefect: {exc}")
        return None

    flow_run_id = run.get("id", "unknown")
    flow_run_name = run.get("name", "unknown")
    log.info("rollback.triggered", label=label, repo=repo_name, flow_run_id=flow_run_id)

    start = time.monotonic()
    last_status = None

    while time.monotonic() - start < MAX_POLL_DURATION:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            run_data = await prefect_api.get_flow_run_status(flow_run_id)
        except Exception:
            log.warning("rollback.poll_error", flow_run_id=flow_run_id, exc_info=True)
            continue

        state = run_data.get("state", {})
        current_status = state.get("type", "UNKNOWN")

        if current_status != last_status:
            last_status = current_status
            await _edit_progress(
                client, channel, msg_ts,
                f"{label}... `{flow_run_name}` is {current_status.lower()}",
            )

        if current_status in TERMINAL_STATES:
            return current_status

    await _edit_progress(
        client, channel, msg_ts,
        f"{label} timed out after {MAX_POLL_DURATION // 60} minutes.",
    )
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def handle_rollback(
    repo_name: str,
    repo_config: dict,
    client,
    channel: str,
    thread_ts: str,
    user_id: str,
    ack_ts: str | None = None,
    target_sha: str | None = None,
) -> None:
    """Execute a rollback for the given repo.

    Called from handlers.py after the rollback guard passes.  Edits the ack
    message in-place as each step completes.
    """
    msg_ts = ack_ts or thread_ts
    repo_dir = repo_config["dir"]

    # ------------------------------------------------------------------
    # Step 1: Determine rollback target SHA
    # ------------------------------------------------------------------
    if target_sha is None:
        last = get_last_deploy(repo_name)
        if last and last.get("pre_sha"):
            target_sha = last["pre_sha"]
        else:
            await _edit_progress(
                client, channel, msg_ts,
                f"No previous deploy found for {repo_name}. "
                f"Specify a SHA: `rollback {repo_name} abc1234`",
            )
            return

    # ------------------------------------------------------------------
    # Step 2: Validate target SHA exists in the repo
    # ------------------------------------------------------------------
    try:
        await _git(repo_dir, "cat-file", "-t", target_sha)
    except RuntimeError:
        await _edit_progress(
            client, channel, msg_ts,
            f"SHA `{target_sha}` not found in {repo_name} repository.",
        )
        return

    # ------------------------------------------------------------------
    # Step 3: Get current SHA (pre-rollback state for auto-roll-forward)
    # ------------------------------------------------------------------
    try:
        current_sha = await _git(repo_dir, "rev-parse", "--short", "HEAD")
    except RuntimeError as exc:
        await _edit_progress(client, channel, msg_ts, f"Failed to get current SHA: {exc}")
        return

    # ------------------------------------------------------------------
    # Step 4: Show rollback info (informational, no gate)
    # ------------------------------------------------------------------
    try:
        commits_being_undone = await _git(repo_dir, "log", "--oneline", f"{target_sha}..HEAD")
    except RuntimeError:
        commits_being_undone = "(could not list commits)"

    info_msg = (
        f"Rolling back {repo_name}...\n"
        f"`{current_sha}` -> `{target_sha}`\n"
    )
    if commits_being_undone:
        info_msg += f"```\n{commits_being_undone}\n```"
    await _edit_progress(client, channel, msg_ts, info_msg)

    # ------------------------------------------------------------------
    # Step 5: Find Prefect deployment
    # ------------------------------------------------------------------
    try:
        deployment_id = await prefect_api.find_deployment_id(
            repo_config["prefect_deployment"],
        )
    except Exception as exc:
        await _edit_progress(client, channel, msg_ts, f"Failed to contact Prefect: {exc}")
        return

    if deployment_id is None:
        await _edit_progress(
            client, channel, msg_ts,
            f"Prefect deployment `{repo_config['prefect_deployment']}` not found.",
        )
        return

    # ------------------------------------------------------------------
    # Step 6: Branch -- self-rollback vs external rollback
    # ------------------------------------------------------------------
    if repo_config.get("self_deploy"):
        await _self_rollback(
            repo_name, repo_config, deployment_id,
            client, channel, thread_ts, msg_ts,
            user_id, current_sha, target_sha, info_msg,
        )
    else:
        await _external_rollback(
            repo_name, repo_config, deployment_id,
            client, channel, msg_ts,
            current_sha, target_sha,
        )


# ---------------------------------------------------------------------------
# super_bot self-rollback
# ---------------------------------------------------------------------------


async def _self_rollback(
    repo_name: str,
    repo_config: dict,
    deployment_id: str,
    client,
    channel: str,
    thread_ts: str,
    msg_ts: str,
    user_id: str,
    current_sha: str,
    target_sha: str,
    info_msg: str,
) -> None:
    """Self-rollback: write state, post message, trigger Prefect, die.

    current_sha is stored in deploy-state so that if the rollback fails on
    restart, the recovery code knows where to roll forward to.
    """
    # Write deploy-state with action="rollback" and pre_sha=current_sha
    write_deploy_state(channel, thread_ts, current_sha, user_id, action="rollback")

    # Pre-restart message
    await _edit_progress(
        client, channel, msg_ts,
        info_msg + "\nRestarting now for rollback. I'll be back shortly.\n"
        "If I don't reply within 30 seconds, check logs: "
        "`sudo journalctl -u superbot -n 50`",
    )

    # Trigger Prefect deploy with target SHA as branch (deploy script does git checkout)
    try:
        run = await prefect_api.create_flow_run(deployment_id, {"branch": target_sha})
        log.info(
            "rollback.self_rollback_triggered",
            repo=repo_name,
            target_sha=target_sha,
            flow_run_id=run.get("id"),
        )
    except Exception as exc:
        log.error("rollback.self_rollback_trigger_failed", error=str(exc))
        await _edit_progress(
            client, channel, msg_ts,
            f"Failed to trigger Prefect rollback: {exc}",
        )

    # No polling -- the bot process will die when systemd restarts it.
    # Post-restart recovery in app.py handles the confirmation message.


# ---------------------------------------------------------------------------
# mic_transformer external rollback
# ---------------------------------------------------------------------------


async def _external_rollback(
    repo_name: str,
    repo_config: dict,
    deployment_id: str,
    client,
    channel: str,
    msg_ts: str,
    current_sha: str,
    target_sha: str,
) -> None:
    """External rollback: trigger Prefect, poll, health check, auto-roll-forward."""

    terminal = await _trigger_and_poll(
        deployment_id, target_sha, client, channel, msg_ts,
        repo_name, f"Rolling back {repo_name}",
    )

    if terminal == "COMPLETED":
        healthy, reason = await _health_check(repo_name, repo_config)
        if healthy:
            record_deploy(repo_name, target_sha[:7], pre_sha=current_sha)
            await _edit_progress(
                client, channel, msg_ts,
                f"Rollback {repo_name} complete. Now on `{target_sha[:7]}`.",
            )
            return
        else:
            # Health check failed -- auto-roll-forward
            log.warning("rollback.health_check_failed", repo=repo_name, reason=reason)
            await _auto_roll_forward(
                repo_name, repo_config, deployment_id,
                client, channel, msg_ts,
                current_sha, reason,
            )
            return

    # Prefect run failed/cancelled/crashed/timed-out -- auto-roll-forward
    log.warning("rollback.prefect_failed", repo=repo_name, terminal_state=terminal)
    await _auto_roll_forward(
        repo_name, repo_config, deployment_id,
        client, channel, msg_ts,
        current_sha, f"Rollback Prefect run ended with: {terminal or 'timeout'}",
    )


async def _auto_roll_forward(
    repo_name: str,
    repo_config: dict,
    deployment_id: str,
    client,
    channel: str,
    msg_ts: str,
    forward_sha: str,
    failure_reason: str,
) -> None:
    """Attempt to roll forward to the pre-rollback SHA after a failed rollback."""
    await _edit_progress(
        client, channel, msg_ts,
        f"Rollback failed: {failure_reason}\n"
        f"Auto-rolling forward to `{forward_sha}`...",
    )

    terminal = await _trigger_and_poll(
        deployment_id, forward_sha, client, channel, msg_ts,
        repo_name, f"Rolling forward {repo_name}",
    )

    if terminal == "COMPLETED":
        healthy, fwd_reason = await _health_check(repo_name, repo_config)
        if healthy:
            await _edit_progress(
                client, channel, msg_ts,
                f"Rollback failed health check. Automatically rolled forward to "
                f"`{forward_sha}`. Reason: {failure_reason}",
            )
            return
        else:
            failure_reason = f"{failure_reason}; roll-forward health check also failed: {fwd_reason}"

    # Roll-forward also failed
    await _edit_progress(
        client, channel, msg_ts,
        f"Rollback failed and auto-roll-forward also failed. "
        f"Manual SSH intervention needed.\n"
        f"Last known state: pre-rollback SHA was `{forward_sha}`, "
        f"rollback target was attempted but failed.\n"
        f"Reason: {failure_reason}",
    )
