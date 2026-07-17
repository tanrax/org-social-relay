from unittest.mock import patch

from django.test import SimpleTestCase

from app.bridge.fetching import BridgeError
from app.bridge.rss import fetch_rss_feed

RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>My Blog</title>
    <link>https://blog.example</link>
    <description>Notes about software</description>
    <language>en-us</language>
    <image>
      <url>https://blog.example/logo.png</url>
      <title>My Blog</title>
      <link>https://blog.example</link>
    </image>
    <item>
      <title>Second article</title>
      <link>https://blog.example/second</link>
      <pubDate>Fri, 02 May 2025 10:00:00 GMT</pubDate>
      <category>emacs</category>
      <category>org mode</category>
      <description>&lt;p&gt;Second &lt;strong&gt;body&lt;/strong&gt;&lt;/p&gt;</description>
    </item>
    <item>
      <title>First article</title>
      <link>https://blog.example/first</link>
      <pubDate>Thu, 01 May 2025 10:00:00 GMT</pubDate>
      <description>First body</description>
    </item>
    <item>
      <title>No date article</title>
      <link>https://blog.example/undated</link>
      <description>Should be skipped</description>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <subtitle>An atom feed</subtitle>
  <link href="https://atom.example"/>
  <entry>
    <title>Atom entry</title>
    <link href="https://atom.example/entry"/>
    <updated>2025-05-01T10:00:00Z</updated>
    <content type="html">&lt;p&gt;Atom body&lt;/p&gt;</content>
  </entry>
</feed>
"""

DUPLICATED_DATES_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Daily</title>
    <link>https://daily.example</link>
    <item>
      <title>Post A</title>
      <link>https://daily.example/a</link>
      <pubDate>Thu, 01 May 2025 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Post B</title>
      <link>https://daily.example/b</link>
      <pubDate>Thu, 01 May 2025 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class FetchRssFeedTest(SimpleTestCase):
    """Test cases for the RSS/Atom fetcher."""

    def test_rss2_metadata_is_extracted(self):
        # Given: A standard RSS 2.0 feed
        with patch("app.bridge.rss.safe_get", return_value=RSS_SAMPLE):
            # When: The feed is fetched
            result = fetch_rss_feed("https://blog.example/feed.xml")

        # Then: The channel metadata maps to profile metadata
        metadata = result["metadata"]
        self.assertEqual(metadata["title"], "My Blog")
        self.assertEqual(metadata["nick"], "My_Blog")
        self.assertEqual(metadata["description"], "Notes about software")
        self.assertEqual(metadata["avatar"], "https://blog.example/logo.png")
        self.assertEqual(metadata["link"], "https://blog.example")
        self.assertEqual(metadata["language"], "en")

    def test_entries_become_posts_with_title_body_and_link(self):
        # Given: A standard RSS 2.0 feed
        with patch("app.bridge.rss.safe_get", return_value=RSS_SAMPLE):
            # When: The feed is fetched
            result = fetch_rss_feed("https://blog.example/feed.xml")

        # Then: Dated entries become posts with UTC IDs
        ids = [post["id"] for post in result["posts"]]
        self.assertEqual(
            ids, ["2025-05-02T10:00:00+00:00", "2025-05-01T10:00:00+00:00"]
        )
        # And: The body has the title heading, converted content and link
        second = result["posts"][0]
        self.assertIn("*** Second article", second["content"])
        self.assertIn("Second *body*", second["content"])
        self.assertIn("[[https://blog.example/second]]", second["content"])
        # And: Categories become tags with spaces replaced
        self.assertEqual(second["tags"], "emacs org-mode")

    def test_entries_without_date_are_skipped(self):
        # Given: A feed with a dateless entry
        with patch("app.bridge.rss.safe_get", return_value=RSS_SAMPLE):
            # When: The feed is fetched
            result = fetch_rss_feed("https://blog.example/feed.xml")

        # Then: The dateless entry is not bridged
        contents = " ".join(post["content"] for post in result["posts"])
        self.assertNotIn("No date article", contents)

    def test_atom_feeds_are_supported(self):
        # Given: An Atom feed
        with patch("app.bridge.rss.safe_get", return_value=ATOM_SAMPLE):
            # When: The feed is fetched
            result = fetch_rss_feed("https://atom.example/feed.atom")

        # Then: Metadata and the entry are bridged
        self.assertEqual(result["metadata"]["title"], "Atom Feed")
        self.assertEqual(len(result["posts"]), 1)
        self.assertEqual(result["posts"][0]["id"], "2025-05-01T10:00:00+00:00")
        self.assertIn("Atom body", result["posts"][0]["content"])

    def test_entries_with_same_date_get_shifted_ids(self):
        # Given: A feed where two entries share the exact same date
        with patch("app.bridge.rss.safe_get", return_value=DUPLICATED_DATES_SAMPLE):
            # When: The feed is fetched
            result = fetch_rss_feed("https://daily.example/feed.xml")

        # Then: Both entries survive with distinct consecutive IDs
        ids = sorted(post["id"] for post in result["posts"])
        self.assertEqual(
            ids, ["2025-05-01T00:00:00+00:00", "2025-05-01T00:00:01+00:00"]
        )

    def test_non_feed_content_raises_bridge_error(self):
        # Given: A URL answering plain HTML
        with patch(
            "app.bridge.rss.safe_get", return_value=b"<html><body>hi</body></html>"
        ):
            # When/Then: Fetching raises a BridgeError
            with self.assertRaises(BridgeError):
                fetch_rss_feed("https://blog.example/not-a-feed")

    def test_feed_without_title_uses_host_as_nick(self):
        # Given: A minimal feed without a channel title
        sample = (
            b'<?xml version="1.0"?><rss version="2.0"><channel>'
            b"<item><title>x</title>"
            b"<pubDate>Thu, 01 May 2025 00:00:00 GMT</pubDate></item>"
            b"</channel></rss>"
        )
        with patch("app.bridge.rss.safe_get", return_value=sample):
            # When: The feed is fetched
            result = fetch_rss_feed("https://blog.example/feed.xml")

        # Then: The nick is derived from the host
        self.assertEqual(result["metadata"]["nick"], "blog_example")
        # And: The title falls back to the source URL
        self.assertEqual(result["metadata"]["title"], "https://blog.example/feed.xml")
