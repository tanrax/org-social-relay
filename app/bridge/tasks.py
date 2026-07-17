"""
Periodic maintenance of bridged accounts.

Only bridges requested recently are refreshed; dormant ones are
reactivated by the inline refresh on their next GET, and bridges nobody
has requested for a long time are deleted together with their profiles.
"""

import logging
from datetime import timedelta

from huey import crontab
from huey.contrib.djhuey import periodic_task

logger = logging.getLogger(__name__)

# Bridges accessed within this window are refreshed periodically
BRIDGE_ACTIVE_DAYS = 7
# Bridges not accessed for this long are deleted
BRIDGE_STALE_DAYS = 90


def _refresh_bridges_impl():
    """
    Refresh every bridge accessed within the active window.

    Returns:
        dict: Counters of refreshed / failed bridges
    """
    from django.utils import timezone

    from .fetching import BridgeError
    from .models import BridgedActivityPubAccount, BridgedRssFeed
    from .store import refresh_activitypub_bridge, refresh_rss_bridge

    cutoff = timezone.now() - timedelta(days=BRIDGE_ACTIVE_DAYS)
    counters = {"refreshed": 0, "failed": 0}

    refresh_plan = [
        (BridgedActivityPubAccount, refresh_activitypub_bridge),
        (BridgedRssFeed, refresh_rss_bridge),
    ]

    for model, refresh in refresh_plan:
        for bridge in model.objects.filter(last_accessed_at__gte=cutoff):
            try:
                refresh(bridge)
                counters["refreshed"] += 1
            except BridgeError as e:
                counters["failed"] += 1
                logger.warning(f"Failed to refresh bridge {bridge}: {e}")
            except Exception as e:
                counters["failed"] += 1
                logger.error(f"Unexpected error refreshing bridge {bridge}: {e}")

    logger.info(
        f"Bridge refresh completed. "
        f"Refreshed: {counters['refreshed']}, Failed: {counters['failed']}"
    )
    return counters


@periodic_task(crontab(minute="*/15"))  # Run every 15 minutes
def refresh_bridges():
    """Periodic task to keep active bridged accounts up to date."""
    import django

    django.setup()

    return _refresh_bridges_impl()


def _cleanup_stale_bridges_impl():
    """
    Delete bridges (and their profiles with all posts) that nobody has
    requested in BRIDGE_STALE_DAYS days.

    Returns:
        int: Number of bridges deleted
    """
    from django.utils import timezone

    from app.feeds.models import Profile

    cutoff = timezone.now() - timedelta(days=BRIDGE_STALE_DAYS)

    # Deleting the Profile cascades to the bridge row and its posts
    stale_profiles = Profile.objects.filter(
        activitypub_bridge__last_accessed_at__lt=cutoff
    ) | Profile.objects.filter(rss_bridge__last_accessed_at__lt=cutoff)

    deleted = 0
    for profile in stale_profiles:
        logger.info(f"Deleting stale bridge profile: {profile.feed}")
        profile.delete()
        deleted += 1

    if deleted:
        logger.info(f"Stale bridge cleanup completed. Deleted {deleted} bridges")
    return deleted


@periodic_task(crontab(day="*/3", hour=3, minute=0))  # Every 3 days at 3 AM
def cleanup_stale_bridges():
    """Periodic task to delete bridges nobody requests anymore."""
    import django

    django.setup()

    return _cleanup_stale_bridges_impl()
