"""
Thin async Prefect API client for deployment lookup and flow run creation.

Wraps synchronous requests calls with asyncio.to_thread for use in the
async bot handlers.
"""

import asyncio

import requests
import structlog

log = structlog.get_logger(__name__)

PREFECT_API = "http://136.111.85.127:4200/api"
PREFECT_AUTH = ("shen", "tofu")
TIMEOUT = 10


async def find_deployment_id(name: str) -> str | None:
    """Look up a Prefect deployment by name. Returns its ID or None."""

    def _call():
        resp = requests.post(
            f"{PREFECT_API}/deployments/filter",
            json={"deployments": {"name": {"any_": [name]}}},
            auth=PREFECT_AUTH,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return results[0]["id"]
        return None

    try:
        return await asyncio.to_thread(_call)
    except Exception:
        log.error("prefect_api.find_deployment_id_failed", name=name, exc_info=True)
        raise


async def create_flow_run(deployment_id: str, parameters: dict) -> dict:
    """Create a flow run for the given deployment. Returns the response JSON."""

    def _call():
        resp = requests.post(
            f"{PREFECT_API}/deployments/{deployment_id}/create_flow_run",
            json={"parameters": parameters},
            auth=PREFECT_AUTH,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    try:
        return await asyncio.to_thread(_call)
    except Exception:
        log.error(
            "prefect_api.create_flow_run_failed",
            deployment_id=deployment_id,
            exc_info=True,
        )
        raise
