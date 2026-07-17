"""
Shared HTTP fetching helpers for the bridge app.

All bridge fetches go through safe_get(), which enforces the same SSRF
protections used for Webmentions, plus a timeout and a response size cap.
"""

import logging

import requests

from app.feeds.webmentions import is_safe_endpoint

logger = logging.getLogger(__name__)

BRIDGE_TIMEOUT = 10
BRIDGE_USER_AGENT = "Org-Social-Relay-Bridge (+https://relay.org-social.org/)"
# Maximum bytes read from any remote response
BRIDGE_MAX_BYTES = 5 * 1024 * 1024


class BridgeError(Exception):
    """A bridge source could not be fetched or understood."""


def safe_get(url, accept=None):
    """
    GET a remote URL with SSRF protection, timeout and size cap.

    Returns the raw bytes of the response body.
    Raises BridgeError on unsafe URLs, network errors or non-2xx codes.
    """
    if not is_safe_endpoint(url):
        raise BridgeError(f"URL is not allowed: {url}")

    headers = {"User-Agent": BRIDGE_USER_AGENT}
    if accept:
        headers["Accept"] = accept

    try:
        response = requests.get(
            url, timeout=BRIDGE_TIMEOUT, headers=headers, stream=True
        )
    except requests.RequestException as e:
        raise BridgeError(f"Could not reach {url}: {e}") from e

    try:
        if not (200 <= response.status_code < 300):
            raise BridgeError(f"HTTP {response.status_code} from {url}")
        return response.raw.read(BRIDGE_MAX_BYTES, decode_content=True)
    finally:
        response.close()
