"""Thin async wrapper around the Apify REST API.

No external Apify SDK — just direct REST calls via httpx. The only entry point
is ``run_actor_sync``, which triggers an actor run and returns its dataset
items once the run completes.
"""

import os

import httpx

from app.scrapers.config import APIFY_API_BASE


class ApifyError(Exception):
    """Raised when an Apify API call returns a non-2xx response."""


async def run_actor_sync(
    actor_id: str,
    input_payload: dict,
    timeout_secs: int = 300,
) -> list[dict]:
    """Trigger an Apify actor run and return the dataset items once complete.

    Uses Apify's run-sync-get-dataset-items endpoint:
        POST {APIFY_API_BASE}/acts/{actor_id}/run-sync-get-dataset-items?token=...

    ``actor_id`` may be given in ``namespace/name`` form; Apify's URL convention
    requires the slash to be written as ``~`` (e.g. ``apify~facebook-groups-
    scraper``), so the conversion is handled here.

    Args:
        actor_id: The Apify actor identifier, e.g. ``apify/facebook-groups-scraper``.
        input_payload: The actor input, sent as the JSON request body.
        timeout_secs: HTTP timeout for the whole request so we never hang forever.

    Returns:
        The parsed JSON array of dataset items (each item is one post).

    Raises:
        ApifyError: On any non-2xx response, with the response body in the message.
    """
    token = os.environ["APIFY_TOKEN"]
    url_actor_id = actor_id.replace("/", "~")
    url = (
        f"{APIFY_API_BASE}/acts/{url_actor_id}"
        f"/run-sync-get-dataset-items?token={token}"
    )

    async with httpx.AsyncClient(timeout=timeout_secs) as client:
        response = await client.post(url, json=input_payload)

    if not response.is_success:
        raise ApifyError(
            f"Apify actor '{actor_id}' returned HTTP {response.status_code}: "
            f"{response.text}"
        )

    return response.json()
