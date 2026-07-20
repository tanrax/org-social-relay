from django.test import SimpleTestCase

from app.bridge.models import is_bridge_feed_url


class IsBridgeFeedUrlTest(SimpleTestCase):
    """Test cases for is_bridge_feed_url using Given/When/Then structure."""

    def test_detects_rss_bridge_url(self):
        """Test an RSS bridge URL is detected as a bridge feed."""
        # Given: The URL of an RSS bridge on any relay
        url = (
            "https://relay.org-social.org/bridge/rss/"
            "?url=https%3A%2F%2Frss.arxiv.org%2Frss%2Fquant-ph"
        )

        # When / Then: It is identified as a bridge feed
        self.assertTrue(is_bridge_feed_url(url))

    def test_detects_activitypub_bridge_url(self):
        """Test an ActivityPub bridge URL is detected as a bridge feed."""
        # Given: The URL of an ActivityPub bridge on any relay
        url = "https://other-relay.org/bridge/activitypub/@user@instance.tld/"

        # When / Then: It is identified as a bridge feed
        self.assertTrue(is_bridge_feed_url(url))

    def test_regular_feed_is_not_a_bridge(self):
        """Test a regular social.org feed is not detected as a bridge."""
        # Given: The URL of a real Org Social feed
        url = "https://example.com/social.org"

        # When / Then: It is not identified as a bridge feed
        self.assertFalse(is_bridge_feed_url(url))

    def test_bridge_marker_in_query_string_is_ignored(self):
        """Test the bridge marker only matches in the URL path."""
        # Given: A real feed whose query string mentions a bridge path
        url = "https://example.com/social.org?note=/bridge/rss/"

        # When / Then: It is not identified as a bridge feed
        self.assertFalse(is_bridge_feed_url(url))
