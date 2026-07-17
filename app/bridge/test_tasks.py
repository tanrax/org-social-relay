from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.bridge.fetching import BridgeError
from app.bridge.models import (
    BridgedActivityPubAccount,
    BridgedRssFeed,
    activitypub_feed_url,
    rss_feed_url,
)
from app.bridge.tasks import (
    BRIDGE_ACTIVE_DAYS,
    BRIDGE_STALE_DAYS,
    _cleanup_stale_bridges_impl,
    _refresh_bridges_impl,
)
from app.feeds.models import Post, Profile


def _make_ap_bridge(handle, accessed_days_ago=0):
    profile = Profile.objects.create(
        feed=activitypub_feed_url(handle),
        title=handle,
        nick=handle.split("@")[0],
        version="v1",
    )
    return BridgedActivityPubAccount.objects.create(
        handle=handle,
        actor_url=f"https://{handle.split('@')[1]}/users/{handle.split('@')[0]}",
        profile=profile,
        last_accessed_at=timezone.now() - timedelta(days=accessed_days_ago),
    )


def _make_rss_bridge(source_url, accessed_days_ago=0):
    profile = Profile.objects.create(
        feed=rss_feed_url(source_url),
        title="Blog",
        nick="blog",
        version="v1",
    )
    return BridgedRssFeed.objects.create(
        source_url=source_url,
        profile=profile,
        last_accessed_at=timezone.now() - timedelta(days=accessed_days_ago),
    )


class RefreshBridgesTest(TestCase):
    """Test cases for the periodic bridge refresh."""

    def test_only_recently_accessed_bridges_are_refreshed(self):
        # Given: An active bridge and a dormant one
        active = _make_ap_bridge("alice@m.example", accessed_days_ago=0)
        _make_ap_bridge("bob@m.example", accessed_days_ago=BRIDGE_ACTIVE_DAYS + 1)

        # When: The refresh task runs
        with (
            patch("app.bridge.store.refresh_activitypub_bridge") as mock_ap,
            patch("app.bridge.store.refresh_rss_bridge"),
        ):
            counters = _refresh_bridges_impl()

        # Then: Only the active bridge is refreshed
        self.assertEqual(counters, {"refreshed": 1, "failed": 0})
        mock_ap.assert_called_once()
        self.assertEqual(mock_ap.call_args[0][0].pk, active.pk)

    def test_both_bridge_types_are_refreshed(self):
        # Given: One active bridge of each type
        _make_ap_bridge("alice@m.example")
        _make_rss_bridge("https://blog.example/feed.xml")

        # When: The refresh task runs
        with (
            patch("app.bridge.store.refresh_activitypub_bridge") as mock_ap,
            patch("app.bridge.store.refresh_rss_bridge") as mock_rss,
        ):
            counters = _refresh_bridges_impl()

        # Then: Both are refreshed
        self.assertEqual(counters, {"refreshed": 2, "failed": 0})
        mock_ap.assert_called_once()
        mock_rss.assert_called_once()

    def test_failed_refreshes_are_counted_and_do_not_stop_the_task(self):
        # Given: Two active bridges, the first origin failing
        _make_ap_bridge("alice@m.example")
        _make_ap_bridge("bob@m.example")

        # When: The refresh task runs
        with (
            patch(
                "app.bridge.store.refresh_activitypub_bridge",
                side_effect=[BridgeError("down"), None],
            ),
            patch("app.bridge.store.refresh_rss_bridge"),
        ):
            counters = _refresh_bridges_impl()

        # Then: The failure is counted and the other bridge still refreshed
        self.assertEqual(counters, {"refreshed": 1, "failed": 1})


class CleanupStaleBridgesTest(TestCase):
    """Test cases for the stale bridge cleanup."""

    def test_stale_bridges_are_deleted_with_profile_and_posts(self):
        # Given: A stale bridge with posts and an active one
        stale = _make_ap_bridge(
            "old@m.example", accessed_days_ago=BRIDGE_STALE_DAYS + 1
        )
        Post.objects.create(
            profile=stale.profile,
            post_id="2025-05-01T10:00:00+00:00",
            content="Bye",
            created_at="2025-05-01T10:00:00+00:00",
        )
        active = _make_ap_bridge("new@m.example", accessed_days_ago=1)

        # When: The cleanup task runs
        deleted = _cleanup_stale_bridges_impl()

        # Then: The stale bridge, its profile and posts are gone
        self.assertEqual(deleted, 1)
        self.assertFalse(BridgedActivityPubAccount.objects.filter(pk=stale.pk).exists())
        self.assertFalse(
            Profile.objects.filter(feed=activitypub_feed_url("old@m.example")).exists()
        )
        self.assertEqual(Post.objects.count(), 0)
        # And: The active bridge survives
        self.assertTrue(BridgedActivityPubAccount.objects.filter(pk=active.pk).exists())

    def test_stale_rss_bridges_are_deleted_too(self):
        # Given: A stale RSS bridge
        _make_rss_bridge(
            "https://blog.example/feed.xml",
            accessed_days_ago=BRIDGE_STALE_DAYS + 1,
        )

        # When: The cleanup task runs
        deleted = _cleanup_stale_bridges_impl()

        # Then: It is deleted
        self.assertEqual(deleted, 1)
        self.assertEqual(BridgedRssFeed.objects.count(), 0)

    def test_nothing_to_delete_returns_zero(self):
        # Given: Only recently accessed bridges
        _make_ap_bridge("alice@m.example", accessed_days_ago=1)

        # When: The cleanup task runs
        deleted = _cleanup_stale_bridges_impl()

        # Then: Nothing is deleted
        self.assertEqual(deleted, 0)
        self.assertEqual(BridgedActivityPubAccount.objects.count(), 1)
