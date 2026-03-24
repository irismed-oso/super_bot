"""
Thin async Prefect API client for deployment lookup and flow run creation.

Uses httpx (already in the venv) for async HTTP calls.
"""

import asyncio

import httpx
import structlog

log = structlog.get_logger(__name__)

PREFECT_API = "http://136.111.85.127:4200/api"
PREFECT_AUTH = ("shen", "tofu")
TIMEOUT = 10


async def find_deployment_id(name: str) -> str | None:
    """Look up a Prefect deployment by name. Returns its ID or None."""
    try:
        async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{PREFECT_API}/deployments/filter",
                json={"deployments": {"name": {"any_": [name]}}},
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                return results[0]["id"]
            return None
    except Exception:
        log.error("prefect_api.find_deployment_id_failed", name=name, exc_info=True)
        raise


async def get_flow_run_status(flow_run_id: str) -> dict:
    """Get the current status of a flow run. Returns the full JSON response.

    Callers typically need ``response["state"]["type"]`` (e.g. COMPLETED,
    FAILED, RUNNING, PENDING, SCHEDULED, CANCELLING, CANCELLED, CRASHED)
    and optionally ``response["state"]["message"]`` for error details.
    """
    try:
        async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=TIMEOUT) as client:
            resp = await client.get(f"{PREFECT_API}/flow_runs/{flow_run_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        log.error("prefect_api.get_flow_run_status_failed", flow_run_id=flow_run_id, exc_info=True)
        raise


async def trigger_batch_crawl(
    locations: list[tuple[str, str]],
    parameters_template: dict,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """Trigger crawl deployments for multiple locations using a single HTTP client.

    Args:
        locations: list of (canonical_name, deployment_name) tuples
        parameters_template: base parameters dict (location key will be overridden)

    Returns:
        (successes, failures) where:
          successes = [(location, flow_run_id, flow_run_name), ...]
          failures  = [(location, error_message), ...]
    """
    successes: list[tuple[str, str, str]] = []
    failures: list[tuple[str, str]] = []

    async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=TIMEOUT) as client:

        async def _trigger_one(canonical: str, dep_name: str) -> None:
            try:
                # Find deployment ID
                resp = await client.post(
                    f"{PREFECT_API}/deployments/filter",
                    json={"deployments": {"name": {"any_": [dep_name]}}},
                )
                resp.raise_for_status()
                results = resp.json()
                if not results:
                    failures.append((canonical, f"Deployment '{dep_name}' not found"))
                    return

                dep_id = results[0]["id"]

                # Create flow run
                params = {**parameters_template, "location": canonical}
                resp2 = await client.post(
                    f"{PREFECT_API}/deployments/{dep_id}/create_flow_run",
                    json={"parameters": params},
                )
                resp2.raise_for_status()
                run = resp2.json()
                successes.append((canonical, run.get("id", "unknown"), run.get("name", "unknown")))
            except Exception as exc:
                failures.append((canonical, str(exc)))

        await asyncio.gather(*[_trigger_one(c, d) for c, d in locations])

    return successes, failures


async def create_flow_run(deployment_id: str, parameters: dict) -> dict:
    """Create a flow run for the given deployment. Returns the response JSON."""
    try:
        async with httpx.AsyncClient(auth=PREFECT_AUTH, timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{PREFECT_API}/deployments/{deployment_id}/create_flow_run",
                json={"parameters": parameters},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        log.error(
            "prefect_api.create_flow_run_failed",
            deployment_id=deployment_id,
            exc_info=True,
        )
        raise
