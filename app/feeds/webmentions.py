"""
Outgoing Webmention support (sender side only).

Implements the sender half of https://www.w3.org/TR/webmention/:
URL extraction from post content, endpoint discovery and notification.
Receiving webmentions is out of scope for the relay.
"""

import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

WEBMENTION_TIMEOUT = 10
WEBMENTION_USER_AGENT = "Org-Social-Relay (+https://relay.org-social.org/)"
# Maximum HTML bytes read while looking for a <link>/<a> endpoint
DISCOVERY_MAX_BYTES = 1024 * 1024

# Org Social mentions ([[org-social:url][nick]]) are handled natively by the
# relay and must never produce webmentions
ORG_SOCIAL_MENTION_RE = re.compile(r"\[\[org-social:[^\]]*\](?:\[[^\]]*\])?\]")
ORG_LINK_RE = re.compile(r"\[\[(https?://[^\]\[]+)\](?:\[[^\]]*\])?\]")
BARE_URL_RE = re.compile(r"https?://[^\s\]\[<>\"']+")
TRAILING_PUNCTUATION = ".,;:!?)'\""


def extract_external_urls(content):
    """
    Extract http(s) URLs from post content, both Org links ([[url]] and
    [[url][description]]) and bare URLs. Org Social mentions are ignored.

    Returns a list of unique URLs in order of appearance.
    """
    if not content:
        return []

    text = ORG_SOCIAL_MENTION_RE.sub(" ", content)

    urls = []
    for match in ORG_LINK_RE.finditer(text):
        urls.append(match.group(1).strip())

    # Remove Org link syntax so bare URL matching does not see them again
    text = ORG_LINK_RE.sub(" ", text)

    for match in BARE_URL_RE.finditer(text):
        urls.append(match.group(0).rstrip(TRAILING_PUNCTUATION))

    unique_urls = []
    seen = set()
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


class _EndpointHTMLParser(HTMLParser):
    """Finds the first <link> or <a> with rel="webmention" in document order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.endpoint = None

    def handle_starttag(self, tag, attrs):
        if self.endpoint is not None or tag not in ("link", "a"):
            return
        attrs_dict = dict(attrs)
        rel = attrs_dict.get("rel") or ""
        if "webmention" in rel.lower().split() and "href" in attrs_dict:
            # An empty href is valid: it resolves to the page URL itself
            self.endpoint = attrs_dict.get("href") or ""


def discover_webmention_endpoint(target_url):
    """
    Discover the Webmention endpoint of a target URL following the spec
    precedence: first HTTP Link header, then first <link>/<a> element in
    document order. Relative endpoints are resolved against the final URL
    after redirects.

    Returns the absolute endpoint URL, or None if the target does not
    advertise one. Raises requests.RequestException on network errors.
    """
    response = requests.get(
        target_url,
        timeout=WEBMENTION_TIMEOUT,
        headers={"User-Agent": WEBMENTION_USER_AGENT},
        stream=True,
    )

    try:
        link_header = response.headers.get("Link", "")
        if link_header:
            for link in requests.utils.parse_header_links(link_header):
                rels = link.get("rel", "").lower().split()
                if "webmention" in rels and "url" in link:
                    return urljoin(response.url, link["url"])

        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            return None

        raw_content = response.raw.read(DISCOVERY_MAX_BYTES, decode_content=True)
        html = raw_content.decode(response.encoding or "utf-8", errors="replace")
    finally:
        response.close()

    parser = _EndpointHTMLParser()
    parser.feed(html)

    if parser.endpoint is None:
        return None
    return urljoin(response.url, parser.endpoint)


def is_safe_endpoint(endpoint_url):
    """
    Reject endpoints that are not plain http(s) or that resolve to loopback,
    private, link-local or otherwise non-global addresses (spec section 4.3).
    """
    parsed = urlparse(endpoint_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False

    try:
        addr_info = socket.getaddrinfo(parsed.hostname, None)
    except (socket.gaierror, UnicodeError):
        return False

    for info in addr_info:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False
    return True


def send_webmention(endpoint_url, source, target):
    """
    POST the webmention as application/x-www-form-urlencoded and return the
    HTTP status code. Raises requests.RequestException on network errors.
    """
    response = requests.post(
        endpoint_url,
        data={"source": source, "target": target},
        timeout=WEBMENTION_TIMEOUT,
        headers={"User-Agent": WEBMENTION_USER_AGENT},
    )
    return response.status_code


def queue_webmentions_for_post(profile, post_id, content):
    """
    Create pending OutgoingWebmention rows for every external URL in a post.

    URLs pointing to registered Org Social feeds (or the author's own feed)
    are skipped: the relay already handles those interactions natively.
    Existing (source, target) pairs are never touched, so a webmention is
    sent at most once even across rescans and post edits.

    Returns the number of newly queued webmentions.
    """
    from .models import Feed, OutgoingWebmention

    urls = extract_external_urls(content)
    if not urls:
        return 0

    source = f"{profile.feed}#{post_id}"
    base_urls = {url.split("#")[0] for url in urls}
    known_feeds = set(
        Feed.objects.filter(url__in=base_urls).values_list("url", flat=True)
    )

    queued = 0
    for url in urls:
        base_url = url.split("#")[0]
        if base_url == profile.feed or base_url in known_feeds:
            continue
        _, created = OutgoingWebmention.objects.get_or_create(source=source, target=url)
        if created:
            queued += 1

    if queued:
        logger.info(f"Queued {queued} webmention(s) for {source}")
    return queued
