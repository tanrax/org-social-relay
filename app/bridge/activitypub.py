"""
ActivityPub fetching for the bridge: WebFinger resolution, actor document
and outbox pagination, normalized into a bridge-agnostic structure.

Only public top-level notes are bridged: replies and boosts (Announce)
are skipped, mirroring what Mastodon exposes in its public RSS feeds.
Instances that require signed fetches (authorized fetch mode) will
answer 401/403 and the account cannot be bridged.
"""

import json
import logging
import re
from urllib.parse import quote

from dateutil import parser as date_parser

from .fetching import BridgeError, safe_get
from .html_to_org import html_to_org, html_to_text

logger = logging.getLogger(__name__)

HANDLE_RE = re.compile(r"^[a-z0-9._-]{1,64}@[a-z0-9-]+(\.[a-z0-9-]+)+$")

ACTIVITYPUB_ACCEPT = (
    "application/activity+json, "
    'application/ld+json; profile="https://www.w3.org/ns/activitystreams"'
)
MAX_POSTS = 40
MAX_OUTBOX_PAGES = 3


def normalize_handle(raw_handle):
    """
    Normalize a user@instance handle: lowercase and without the optional
    leading @. Returns None if the result is not a valid handle.
    """
    handle = (raw_handle or "").strip().lstrip("@").lower()
    if not HANDLE_RE.match(handle):
        return None
    return handle


def _get_json(url, description):
    try:
        return json.loads(safe_get(url, accept=ACTIVITYPUB_ACCEPT))
    except json.JSONDecodeError as e:
        raise BridgeError(f"Invalid JSON in {description} at {url}") from e


def _resolve_actor_url(user, instance):
    """Resolve the actor URL of user@instance through WebFinger."""
    resource = quote(f"acct:{user}@{instance}", safe="")
    webfinger_url = f"https://{instance}/.well-known/webfinger?resource={resource}"
    try:
        document = json.loads(safe_get(webfinger_url, accept="application/jrd+json"))
    except json.JSONDecodeError as e:
        raise BridgeError(f"Invalid WebFinger response from {instance}") from e

    for link in document.get("links", []):
        if not isinstance(link, dict) or link.get("rel") != "self":
            continue
        if "activity+json" in (link.get("type") or "") and link.get("href"):
            return link["href"]
    for link in document.get("links", []):
        if isinstance(link, dict) and link.get("rel") == "self" and link.get("href"):
            return link["href"]
    raise BridgeError(f"No ActivityPub actor found for {user}@{instance}")


def _format_post_id(published):
    """Convert an ActivityPub published date to an Org Social post ID."""
    parsed = date_parser.parse(published)
    if parsed.tzinfo is None:
        return None
    from datetime import timezone as dt_timezone

    return parsed.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _note_to_post(note):
    """Normalize an ActivityPub Note object into a bridge post dict."""
    published = note.get("published")
    if not published:
        return None
    try:
        post_id = _format_post_id(published)
    except (ValueError, OverflowError):
        logger.warning(f"Skipping note with unparseable date: {published}")
        return None
    if post_id is None:
        return None

    parts = []
    summary = note.get("summary")
    if summary:
        parts.append(f"CW: {html_to_text(summary)}")
    body = html_to_org(note.get("content") or "")
    if body:
        parts.append(body)
    attachment_links = []
    for attachment in note.get("attachment", []):
        if isinstance(attachment, dict) and attachment.get("url"):
            attachment_links.append(f"[[{attachment['url']}]]")
    if attachment_links:
        parts.append("\n".join(attachment_links))

    tags = []
    for tag in note.get("tag", []):
        if isinstance(tag, dict) and tag.get("type") == "Hashtag" and tag.get("name"):
            tags.append(tag["name"].lstrip("#"))

    language = ""
    content_map = note.get("contentMap")
    if isinstance(content_map, dict) and content_map:
        language = next(iter(content_map.keys()), "")

    return {
        "id": post_id,
        "content": "\n\n".join(parts),
        "tags": " ".join(tags),
        "language": language,
    }


def _collect_outbox_posts(outbox_url):
    """Walk the outbox pages collecting public top-level notes."""
    document = _get_json(outbox_url, "outbox")

    if "orderedItems" in document:
        page = document
    else:
        first = document.get("first")
        if isinstance(first, str):
            page = _get_json(first, "outbox page")
        elif isinstance(first, dict):
            page = first
        else:
            return []

    posts = []
    seen_ids = set()
    pages_read = 0

    while page and pages_read < MAX_OUTBOX_PAGES and len(posts) < MAX_POSTS:
        pages_read += 1
        for item in page.get("orderedItems", []):
            if len(posts) >= MAX_POSTS:
                break
            if not isinstance(item, dict) or item.get("type") != "Create":
                continue
            note = item.get("object")
            if not isinstance(note, dict) or note.get("type") != "Note":
                continue
            if note.get("inReplyTo"):
                continue
            post = _note_to_post(note)
            if post is None or post["id"] in seen_ids:
                continue
            seen_ids.add(post["id"])
            posts.append(post)

        next_url = page.get("next")
        if isinstance(next_url, str) and len(posts) < MAX_POSTS:
            page = _get_json(next_url, "outbox page")
        else:
            page = None

    return posts


def _actor_avatar(actor):
    icon = actor.get("icon")
    if isinstance(icon, list):
        icon = icon[0] if icon else None
    if isinstance(icon, dict):
        return icon.get("url") or ""
    if isinstance(icon, str):
        return icon
    return ""


def fetch_account(user, instance):
    """
    Fetch an ActivityPub account and normalize it for the bridge.

    Returns a dict with actor_url, outbox_url, metadata and posts.
    Raises BridgeError when the account cannot be fetched.
    """
    actor_url = _resolve_actor_url(user, instance)
    actor = _get_json(actor_url, "actor document")

    outbox_url = actor.get("outbox")
    nick = actor.get("preferredUsername") or user
    metadata = {
        "title": actor.get("name") or f"{nick}@{instance}",
        "nick": nick,
        "description": html_to_text(actor.get("summary") or ""),
        "avatar": _actor_avatar(actor),
        "link": actor.get("url") or actor_url,
    }

    posts = []
    if isinstance(outbox_url, str) and outbox_url:
        posts = _collect_outbox_posts(outbox_url)
    else:
        logger.warning(f"Actor {actor_url} has no outbox")
        outbox_url = ""

    return {
        "actor_url": actor_url,
        "outbox_url": outbox_url,
        "metadata": metadata,
        "posts": posts,
    }
