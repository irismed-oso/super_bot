"""
Manage payer portal credentials in GCP Secret Manager.

Provides functions to update VSP and EyeMed credentials for any location.
Secret naming follows the same convention as mic_transformer's PayerLogin:
    eyemed-creds-{slug}  and  vsp-creds-{slug}
where slug is the lowercased, hyphen-separated location name.
"""

import json
import re

import structlog

log = structlog.get_logger(__name__)

GCP_PROJECT_ID = "oso-fe"

# Valid payer types
VALID_PAYERS = {"eyemed", "vsp"}

# Lazy-initialized client singleton (same pattern as mic_transformer)
_client = None


def _get_client():
    global _client
    if _client is None:
        from google.cloud import secretmanager
        _client = secretmanager.SecretManagerServiceClient()
    return _client


def _to_secret_slug(location: str) -> str:
    """Convert location name to a valid GCP Secret Manager secret ID slug.

    Same logic as mic_transformer's PayerLogin._to_secret_slug().
    """
    slug = location.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def _secret_id(payer: str, location: str) -> str:
    """Build the full secret ID, e.g. 'eyemed-creds-peg'."""
    return f"{payer}-creds-{_to_secret_slug(location)}"


def update_credentials(payer: str, location: str, username: str, password: str) -> str:
    """Update (or create) credentials in GCP Secret Manager.

    Args:
        payer: 'eyemed' or 'vsp'
        location: Canonical location name (e.g. 'PEG', 'ECEC')
        username: Portal username
        password: Portal password

    Returns:
        Human-readable result message

    Raises:
        Exception: On GCP API errors
    """
    client = _get_client()
    secret_id = _secret_id(payer, location)
    parent = f"projects/{GCP_PROJECT_ID}"
    secret_path = f"{parent}/secrets/{secret_id}"
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")

    # Try to add a new version; create the secret first if it doesn't exist
    try:
        client.add_secret_version(
            request={"parent": secret_path, "payload": {"data": payload}}
        )
    except Exception as exc:
        if "NOT_FOUND" in str(exc):
            log.info("credential_manager.creating_secret", secret_id=secret_id)
            client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
            client.add_secret_version(
                request={"parent": secret_path, "payload": {"data": payload}}
            )
        else:
            raise

    log.info(
        "credential_manager.updated",
        payer=payer,
        location=location,
        secret_id=secret_id,
    )
    return secret_id


def get_credentials(payer: str, location: str) -> dict | None:
    """Read current credentials from Secret Manager. Returns None if not found."""
    client = _get_client()
    secret_id = _secret_id(payer, location)
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        return json.loads(response.payload.data.decode("utf-8"))
    except Exception:
        return None
