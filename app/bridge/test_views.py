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
from app.feeds.models import Profile

AP_FEED_PATH = "/bridge/activitypub/@alice@m.example/"
RSS_SOURCE_URL = "https://blog.example/feed.xml"


def _ap_data(posts=None):
    return {
        "actor_url": "https://m.example/users/alice",
        "outbox_url": "https://m.example/users/alice/outbox",
        "metadata": {
            "title": "Alice",
            "nick": "alice",
            "description": "Bio",
            "avatar": "https://m.example/avatar.png",
            "link": "https://m.example/@alice",
        },
        "posts": posts
        if posts is not None
        else [
            {
                "id": "2025-05-01T10:00:00+00:00",
                "content": "Hello from the fediverse",
                "tags": "",
                "language": "",
            }
        ],
    }


def _rss_data():
    return {
        "metadata": {
            "title": "My Blog",
            "nick": "My_Blog",
            "description": "Notes",
            "avatar": "",
            "link": "https://blog.example",
            "language": "en",
        },
        "posts": [
            {
                "id": "2025-05-01T10:00:00+00:00",
                "content": "*** First article\n\nBody\n\n[[https://blog.example/first]]",
                "tags": "",
                "language": "",
            }
        ],
    }


class ActivityPubBridgeFeedViewTest(TestCase):
    """Test cases for the ActivityPub virtual feed endpoint."""

    def test_first_get_registers_account_and_serves_org_file(self):
        # Given: A reachable ActivityPub account not yet bridged
        with patch(
            "app.bridge.activitypub.fetch_account", return_value=_ap_data()
        ) as mock_fetch:
            # When: The virtual feed is requested for the first time
            response = self.client.get(AP_FEED_PATH)

        # Then: The org file is served as plain text
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        content = response.content.decode()
        self.assertIn("#+TITLE: Alice", content)
        self.assertIn("#+NICK: alice", content)
        self.assertIn("** 2025-05-01T10:00:00+00:00", content)
        self.assertIn("Hello from the fediverse", content)
        # And: The bridge and its profile are stored
        mock_fetch.assert_called_once_with("alice", "m.example")
        bridge = BridgedActivityPubAccount.objects.get(handle="alice@m.example")
        self.assertEqual(bridge.profile.feed, activitypub_feed_url("alice@m.example"))

    def test_second_get_is_served_from_database_without_network(self):
        # Given: An already bridged account
        with patch(
            "app.bridge.activitypub.fetch_account", return_value=_ap_data()
        ) as mock_fetch:
            self.client.get(AP_FEED_PATH)

            # When: The feed is requested again shortly after
            response = self.client.get(AP_FEED_PATH)

        # Then: The response is correct and no second fetch happened
        self.assertEqual(response.status_code, 200)
        self.assertIn("Hello from the fediverse", response.content.decode())
        self.assertEqual(mock_fetch.call_count, 1)

    def test_non_canonical_handles_redirect_to_canonical_url(self):
        # Given: Handle spellings with capitals or without the @ prefix
        for path in (
            "/bridge/activitypub/@Alice@M.Example/",
            "/bridge/activitypub/alice@m.example/",
        ):
            # When: The non-canonical URL is requested
            response = self.client.get(path)

            # Then: A permanent redirect points to the canonical URL
            self.assertEqual(response.status_code, 301, path)
            self.assertEqual(response["Location"], AP_FEED_PATH)

    def test_invalid_handle_returns_400(self):
        # Given: A handle without an instance part
        # When: The feed is requested
        response = self.client.get("/bridge/activitypub/@alice/")

        # Then: The request is rejected
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["type"], "Error")

    def test_unreachable_account_returns_502(self):
        # Given: An account whose instance cannot be reached
        with patch(
            "app.bridge.activitypub.fetch_account",
            side_effect=BridgeError("connection refused"),
        ):
            # When: The feed is requested
            response = self.client.get(AP_FEED_PATH)

        # Then: A bad gateway error with the envelope format is returned
        self.assertEqual(response.status_code, 502)
        body = response.json()
        self.assertEqual(body["type"], "Error")
        self.assertIsNone(body["data"])
        # And: Nothing was stored
        self.assertEqual(BridgedActivityPubAccount.objects.count(), 0)

    def test_stale_bridge_is_refreshed_inline_on_access(self):
        # Given: A bridged account whose data is older than a day
        with patch("app.bridge.activitypub.fetch_account", return_value=_ap_data()):
            self.client.get(AP_FEED_PATH)
        bridge = BridgedActivityPubAccount.objects.get(handle="alice@m.example")
        bridge.last_refreshed_at = timezone.now() - timedelta(days=2)
        bridge.save()

        new_posts = _ap_data(
            posts=[
                {
                    "id": "2025-05-05T10:00:00+00:00",
                    "content": "Fresh post",
                    "tags": "",
                    "language": "",
                }
            ]
        )

        # When: The feed is requested again
        with patch(
            "app.bridge.activitypub.fetch_account", return_value=new_posts
        ) as mock_fetch:
            response = self.client.get(AP_FEED_PATH)

        # Then: The origin was fetched again and the new post is served
        mock_fetch.assert_called_once()
        self.assertIn("Fresh post", response.content.decode())
        bridge.refresh_from_db()
        self.assertGreater(
            bridge.last_refreshed_at, timezone.now() - timedelta(minutes=1)
        )

    def test_failed_inline_refresh_serves_stored_copy(self):
        # Given: A stale bridge whose origin is now unreachable
        with patch("app.bridge.activitypub.fetch_account", return_value=_ap_data()):
            self.client.get(AP_FEED_PATH)
        bridge = BridgedActivityPubAccount.objects.get(handle="alice@m.example")
        bridge.last_refreshed_at = timezone.now() - timedelta(days=2)
        bridge.save()

        # When: The feed is requested while the origin fails
        with patch(
            "app.bridge.activitypub.fetch_account",
            side_effect=BridgeError("down"),
        ):
            response = self.client.get(AP_FEED_PATH)

        # Then: The stored copy is served anyway
        self.assertEqual(response.status_code, 200)
        self.assertIn("Hello from the fediverse", response.content.decode())

    def test_bridged_profile_is_available_through_profile_endpoint(self):
        # Given: A bridged account
        with patch("app.bridge.activitypub.fetch_account", return_value=_ap_data()):
            self.client.get(AP_FEED_PATH)

        # When: The existing /profile/ endpoint is queried with the bridge URL
        feed_url = activitypub_feed_url("alice@m.example")
        response = self.client.get("/profile/", {"feed": feed_url})

        # Then: The bridged profile is returned like any other profile
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["type"], "Success")


class ActivityPubBridgeListViewTest(TestCase):
    """Test cases for the bridged accounts listing."""

    def test_lists_bridged_accounts_with_feed_urls(self):
        # Given: A bridged account
        profile = Profile.objects.create(
            feed=activitypub_feed_url("alice@m.example"),
            title="Alice",
            nick="alice",
            version="v1",
        )
        BridgedActivityPubAccount.objects.create(
            handle="alice@m.example",
            actor_url="https://m.example/users/alice",
            profile=profile,
            last_accessed_at=timezone.now(),
        )

        # When: The list is requested
        response = self.client.get("/bridge/activitypub/")

        # Then: The account and its virtual feed URL are listed
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["type"], "Success")
        self.assertEqual(
            body["data"],
            [
                {
                    "handle": "@alice@m.example",
                    "feed": activitypub_feed_url("alice@m.example"),
                }
            ],
        )


class RssBridgeViewTest(TestCase):
    """Test cases for the RSS bridge endpoint."""

    def test_first_get_registers_feed_and_serves_org_file(self):
        # Given: A reachable RSS feed not yet bridged
        with patch(
            "app.bridge.rss.fetch_rss_feed", return_value=_rss_data()
        ) as mock_fetch:
            # When: The virtual feed is requested for the first time
            response = self.client.get("/bridge/rss/", {"url": RSS_SOURCE_URL})

        # Then: The org file is served as plain text
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        content = response.content.decode()
        self.assertIn("#+TITLE: My Blog", content)
        self.assertIn("#+NICK: My_Blog", content)
        self.assertIn("*** First article", content)
        # And: The bridge is stored
        mock_fetch.assert_called_once_with(RSS_SOURCE_URL)
        self.assertTrue(
            BridgedRssFeed.objects.filter(source_url=RSS_SOURCE_URL).exists()
        )

    def test_second_get_is_served_from_database_without_network(self):
        # Given: An already bridged RSS feed
        with patch(
            "app.bridge.rss.fetch_rss_feed", return_value=_rss_data()
        ) as mock_fetch:
            self.client.get("/bridge/rss/", {"url": RSS_SOURCE_URL})

            # When: The feed is requested again shortly after
            response = self.client.get("/bridge/rss/", {"url": RSS_SOURCE_URL})

        # Then: The response is correct and no second fetch happened
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_fetch.call_count, 1)

    def test_without_url_parameter_lists_bridged_feeds(self):
        # Given: A bridged RSS feed
        profile = Profile.objects.create(
            feed=rss_feed_url(RSS_SOURCE_URL),
            title="My Blog",
            nick="My_Blog",
            version="v1",
        )
        BridgedRssFeed.objects.create(
            source_url=RSS_SOURCE_URL,
            profile=profile,
            last_accessed_at=timezone.now(),
        )

        # When: The endpoint is requested without url
        response = self.client.get("/bridge/rss/")

        # Then: The bridged feeds are listed
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["data"],
            [{"url": RSS_SOURCE_URL, "feed": rss_feed_url(RSS_SOURCE_URL)}],
        )

    def test_invalid_url_parameter_returns_400(self):
        # Given: Invalid url parameters
        too_long = "https://example.com/" + "a" * 500

        for bad_url in ("ftp://example.com/feed", "not-a-url", too_long):
            # When: The endpoint is requested
            response = self.client.get("/bridge/rss/", {"url": bad_url})

            # Then: The request is rejected
            self.assertEqual(response.status_code, 400, bad_url)
            self.assertEqual(response.json()["type"], "Error")

    def test_unreachable_feed_returns_502(self):
        # Given: A feed URL that cannot be fetched
        with patch(
            "app.bridge.rss.fetch_rss_feed",
            side_effect=BridgeError("timeout"),
        ):
            # When: The endpoint is requested
            response = self.client.get("/bridge/rss/", {"url": RSS_SOURCE_URL})

        # Then: A bad gateway error is returned and nothing is stored
        self.assertEqual(response.status_code, 502)
        self.assertEqual(BridgedRssFeed.objects.count(), 0)


class BridgeIndexViewTest(TestCase):
    """Test cases for the bridge index endpoint."""

    def test_index_exposes_bridge_links(self):
        # When: The bridge index is requested
        response = self.client.get("/bridge/")

        # Then: Both bridge types are discoverable
        self.assertEqual(response.status_code, 200)
        links = response.json()["_links"]
        self.assertIn("activitypub-feed", links)
        self.assertIn("rss-feed", links)

    def test_root_endpoint_links_to_bridges(self):
        # When: The relay root is requested
        response = self.client.get("/")

        # Then: The bridge endpoints are listed
        links = response.json()["_links"]
        self.assertIn("bridge", links)
        self.assertIn("bridge-activitypub", links)
        self.assertIn("bridge-rss", links)


class LastAccessedTrackingTest(TestCase):
    """Test cases for access tracking used by refresh and cleanup."""

    def test_old_last_accessed_is_updated_on_get(self):
        # Given: A bridge last accessed two days ago
        profile = Profile.objects.create(
            feed=activitypub_feed_url("alice@m.example"),
            title="Alice",
            nick="alice",
            version="v1",
        )
        old_access = timezone.now() - timedelta(days=2)
        bridge = BridgedActivityPubAccount.objects.create(
            handle="alice@m.example",
            actor_url="https://m.example/users/alice",
            profile=profile,
            last_accessed_at=old_access,
            last_refreshed_at=timezone.now(),
        )

        # When: The feed is requested
        self.client.get(AP_FEED_PATH)

        # Then: last_accessed_at moves forward
        bridge.refresh_from_db()
        self.assertGreater(bridge.last_accessed_at, old_access)
