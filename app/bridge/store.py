"""
Persistence and orchestration for bridged accounts.

Normalized bridge data (from activitypub.py or rss.py) is stored in the
same Profile/Post tables used for real Org Social feeds, so every
existing relay endpoint (/profile/, /search/, /rss.xml, ...) works on
bridged accounts transparently.

Bridged posts never queue Webmentions nor publish notifications: the
content belongs to external authors, the relay only mirrors it.
"""

import hashlib
import logging

from dateutil import parser as date_parser
from django.utils import timezone

from app.feeds.models import Post, Profile, ProfileLink

from . import activitypub, rss
from .models import (
    BridgedActivityPubAccount,
    BridgedRssFeed,
    activitypub_feed_url,
    rss_feed_url,
)

logger = logging.getLogger(__name__)


def store_bridge_data(feed_url, data):
    """
    Create or update the Profile and Posts of a bridged account.

    Args:
        feed_url: public URL of the virtual feed on this relay
        data: normalized dict with "metadata" and "posts"

    Returns:
        Profile: the stored profile
    """
    metadata = data["metadata"]
    posts_data = data["posts"]

    content_hash = hashlib.md5(f"{metadata}{posts_data}".encode()).hexdigest()

    nick = " ".join((metadata.get("nick") or "").split()).replace(" ", "_")
    profile_fields = {
        "title": metadata.get("title", ""),
        "nick": nick,
        "description": metadata.get("description", ""),
        "avatar": metadata.get("avatar", ""),
        "language": metadata.get("language", ""),
        "version": content_hash,
    }

    profile, created = Profile.objects.get_or_create(
        feed=feed_url, defaults=profile_fields
    )

    if not created:
        if profile.version == content_hash:
            return profile
        for field, value in profile_fields.items():
            setattr(profile, field, value)
        profile.save()

    profile.links.all().delete()
    link = (metadata.get("link") or "").strip()
    if link:
        ProfileLink.objects.create(profile=profile, url=link)

    fetched_ids = set()
    oldest_created_at = None
    for post_data in posts_data:
        post_id = post_data["id"]
        try:
            post_created_at = date_parser.parse(post_id)
        except (ValueError, OverflowError):
            logger.warning(f"Skipping bridged post with invalid ID: {post_id}")
            continue

        fetched_ids.add(post_id)
        if oldest_created_at is None or post_created_at < oldest_created_at:
            oldest_created_at = post_created_at

        post, post_created = Post.objects.get_or_create(
            profile=profile,
            post_id=post_id,
            defaults={
                "content": post_data["content"],
                "tags": post_data.get("tags", "")[:500],
                "language": post_data.get("language", "")[:10],
                "created_at": post_created_at,
            },
        )
        if not post_created:
            post.content = post_data["content"]
            post.tags = post_data.get("tags", "")[:500]
            post.language = post_data.get("language", "")[:10]
            post.save()

    # Posts deleted at the origin disappear from the fetched window;
    # remove them, but never touch posts older than what was fetched
    if fetched_ids and oldest_created_at is not None:
        Post.objects.filter(profile=profile, created_at__gte=oldest_created_at).exclude(
            post_id__in=fetched_ids
        ).delete()

    return profile


def create_activitypub_bridge(handle):
    """
    Fetch an ActivityPub account for the first time and create its bridge.

    Raises BridgeError when the account cannot be fetched.
    """
    user, instance = handle.split("@", 1)
    data = activitypub.fetch_account(user, instance)

    profile = store_bridge_data(activitypub_feed_url(handle), data)

    now = timezone.now()
    bridge = BridgedActivityPubAccount.objects.create(
        handle=handle,
        actor_url=data["actor_url"],
        outbox_url=data["outbox_url"],
        profile=profile,
        last_refreshed_at=now,
        last_accessed_at=now,
    )
    logger.info(f"Created ActivityPub bridge for @{handle}")
    return bridge


def refresh_activitypub_bridge(bridge):
    """
    Refetch a bridged ActivityPub account and update its stored data.

    Raises BridgeError when the origin cannot be fetched.
    """
    user, instance = bridge.handle.split("@", 1)
    data = activitypub.fetch_account(user, instance)
    store_bridge_data(bridge.feed_url, data)

    bridge.actor_url = data["actor_url"] or bridge.actor_url
    bridge.outbox_url = data["outbox_url"] or bridge.outbox_url
    bridge.last_refreshed_at = timezone.now()
    bridge.save()


def create_rss_bridge(source_url):
    """
    Fetch an RSS/Atom feed for the first time and create its bridge.

    Raises BridgeError when the feed cannot be fetched.
    """
    data = rss.fetch_rss_feed(source_url)

    profile = store_bridge_data(rss_feed_url(source_url), data)

    now = timezone.now()
    bridge = BridgedRssFeed.objects.create(
        source_url=source_url,
        profile=profile,
        last_refreshed_at=now,
        last_accessed_at=now,
    )
    logger.info(f"Created RSS bridge for {source_url}")
    return bridge


def refresh_rss_bridge(bridge):
    """
    Refetch a bridged RSS feed and update its stored data.

    Raises BridgeError when the origin cannot be fetched.
    """
    data = rss.fetch_rss_feed(bridge.source_url)
    store_bridge_data(bridge.feed_url, data)

    bridge.last_refreshed_at = timezone.now()
    bridge.save()
