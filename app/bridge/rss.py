"""
RSS/Atom fetching for the bridge, normalized into the same structure
used by the ActivityPub bridge.

Each entry becomes a post whose body is the entry title as an Org
sub-heading (***), the converted entry content, and a link to the
original article.
"""

import calendar
import logging
import re
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlparse

import feedparser

from .fetching import BridgeError, safe_get
from .html_to_org import html_to_org

logger = logging.getLogger(__name__)

MAX_POSTS = 40

_NICK_ALLOWED_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _derive_nick(title, source_url):
    """Build a spaces-free nick from the feed title or the feed host."""
    candidate = _NICK_ALLOWED_RE.sub("_", (title or "").strip()).strip("_")
    if candidate:
        return candidate
    host = urlparse(source_url).hostname or "feed"
    return host.replace(".", "_")


def _entry_post_id(entry):
    """Org Social post ID (UTC RFC 3339) from the entry date, or None."""
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed_time:
        return None
    timestamp = calendar.timegm(parsed_time)
    return datetime.fromtimestamp(timestamp, dt_timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00"
    )


def _next_free_id(post_id, seen_ids):
    """
    Entries sharing the same timestamp (e.g. date-only feeds) get IDs
    shifted forward one second at a time so no post is lost.
    """
    while post_id in seen_ids:
        parsed = datetime.strptime(post_id, "%Y-%m-%dT%H:%M:%S+00:00")
        shifted = parsed.timestamp() + 1
        post_id = datetime.fromtimestamp(shifted, dt_timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )
    return post_id


def _entry_body(entry):
    contents = entry.get("content") or []
    if contents and contents[0].get("value"):
        html = contents[0]["value"]
    else:
        html = entry.get("summary") or ""
    return html_to_org(html)


def _entry_to_post(entry, seen_ids):
    post_id = _entry_post_id(entry)
    if post_id is None:
        logger.warning(
            f"Skipping RSS entry without date: {entry.get('link', '(no link)')}"
        )
        return None
    post_id = _next_free_id(post_id, seen_ids)

    parts = []
    title = " ".join((entry.get("title") or "").split())
    if title:
        parts.append(f"*** {title}")
    body = _entry_body(entry)
    if body:
        parts.append(body)
    link = (entry.get("link") or "").strip()
    if link and "]" not in link:
        parts.append(f"[[{link}]]")

    tags = " ".join(
        tag.get("term", "").strip().replace(" ", "-")
        for tag in entry.get("tags", [])
        if tag.get("term")
    )

    return {
        "id": post_id,
        "content": "\n\n".join(parts),
        "tags": tags,
        "language": "",
    }


def fetch_rss_feed(source_url):
    """
    Fetch an RSS/Atom feed and normalize it for the bridge.

    Returns a dict with metadata and posts.
    Raises BridgeError when the feed cannot be fetched or parsed.
    """
    raw = safe_get(source_url)
    document = feedparser.parse(raw)

    feed_info = document.get("feed", {})
    if not document.get("entries") and not feed_info.get("title"):
        raise BridgeError(f"Not a valid RSS/Atom feed: {source_url}")

    title = " ".join((feed_info.get("title") or "").split())
    image = feed_info.get("image") or {}
    metadata = {
        "title": title or source_url,
        "nick": _derive_nick(title, source_url),
        "description": " ".join((feed_info.get("subtitle") or "").split()),
        "avatar": image.get("href", ""),
        "link": feed_info.get("link") or source_url,
        "language": (feed_info.get("language") or "").split("-")[0],
    }

    posts = []
    seen_ids = set()
    for entry in document.get("entries", [])[:MAX_POSTS]:
        post = _entry_to_post(entry, seen_ids)
        if post is None:
            continue
        seen_ids.add(post["id"])
        posts.append(post)

    return {"metadata": metadata, "posts": posts}
