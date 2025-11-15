from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from xml.etree import ElementTree as ET

from app.feeds.models import Profile, Post


class RSSFeedTest(TestCase):
    """Test cases for the RSS Feed using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.rss_url = "/rss.xml"

        # Create test profiles
        self.profile1 = Profile.objects.create(
            feed="https://example.com/social.org",
            title="Example Profile",
            nick="example_user",
            description="Test profile 1",
        )
        self.profile2 = Profile.objects.create(
            feed="https://test.com/social.org",
            title="Test Profile",
            nick="test_user",
            description="Test profile 2",
        )
        self.profile3 = Profile.objects.create(
            feed="https://third.com/social.org",
            title="Third Profile",
            nick="third_user",
            description="Test profile 3",
        )

        # Create test posts with different content and tags
        self.post1 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="This post is about Emacs and org-mode",
            tags="emacs org-mode",
        )

        self.post2 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="Learning Python programming language",
            tags="python programming",
        )

        self.post3 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T14:00:00+00:00",
            content="Django web framework with Python",
            tags="django python web",
        )

        self.post4 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T15:00:00+00:00",
            content="Emacs configuration and setup",
            tags="emacs configuration",
        )

        self.post5 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T16:00:00+00:00",
            content="JavaScript and React development",
            tags="javascript react frontend",
        )

    def test_rss_feed_all_posts_success(self):
        """Test GET /rss.xml returns RSS feed with all posts."""
        # Given: Posts exist in the database

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Then: Should return 200 and valid RSS
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/rss+xml; charset=utf-8')

        # Parse XML and verify structure
        root = ET.fromstring(response.content)
        self.assertEqual(root.tag, 'rss')
        self.assertEqual(root.get('version'), '2.0')

        # Verify channel
        channel = root.find('channel')
        self.assertIsNotNone(channel)

        # Verify title
        title = channel.find('title')
        self.assertIsNotNone(title)
        self.assertEqual(title.text, 'Org Social Relay - Latest Posts')

        # Verify items
        items = channel.findall('item')
        self.assertEqual(len(items), 5)  # All 5 posts

        # Verify first item (most recent)
        first_item = items[0]
        guid = first_item.find('guid')
        self.assertIsNotNone(guid)
        self.assertIn(self.post5.post_id, guid.text)

    def test_rss_feed_filtered_by_tag(self):
        """Test GET /rss.xml?tag=<tag> returns RSS feed filtered by tag."""
        # Given: Posts with various tags

        # When: We request the RSS feed filtered by tag "emacs"
        response = self.client.get(self.rss_url, {'tag': 'emacs'})

        # Then: Should return 200 and filtered RSS
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')

        # Verify title includes tag
        title = channel.find('title')
        self.assertIn('emacs', title.text.lower())

        # Verify only posts with "emacs" tag are included
        items = channel.findall('item')
        self.assertEqual(len(items), 2)  # post1 and post4

        # Verify all items have the emacs tag
        for item in items:
            categories = [cat.text for cat in item.findall('category')]
            self.assertIn('emacs', categories)

    def test_rss_feed_filtered_by_feed(self):
        """Test GET /rss.xml?feed=<feed_url> returns RSS feed filtered by author feed."""
        # Given: Posts from different profiles

        # When: We request the RSS feed filtered by profile1's feed
        response = self.client.get(self.rss_url, {'feed': self.profile1.feed})

        # Then: Should return 200 and filtered RSS
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')

        # Verify title includes feed
        title = channel.find('title')
        self.assertIn(self.profile1.feed, title.text)

        # Verify only posts from profile1 are included
        items = channel.findall('item')
        self.assertEqual(len(items), 2)  # post1 and post4

        # Verify all items are from profile1
        for item in items:
            link = item.find('link')
            self.assertIn(self.profile1.feed, link.text)

    def test_rss_feed_item_structure(self):
        """Test that RSS feed items have correct structure."""
        # Given: Posts exist

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Then: Each item should have required fields
        for item in items:
            # Required fields
            self.assertIsNotNone(item.find('title'))
            self.assertIsNotNone(item.find('link'))
            self.assertIsNotNone(item.find('description'))
            self.assertIsNotNone(item.find('pubDate'))
            self.assertIsNotNone(item.find('guid'))
            self.assertIsNotNone(item.find('author'))

    def test_rss_feed_limit_200_posts(self):
        """Test that RSS feed is limited to 200 posts as per specification."""
        # Given: More than 200 posts
        for i in range(201):
            Post.objects.create(
                profile=self.profile1,
                post_id=f"2025-01-02T{i // 60:02d}:{i % 60:02d}:00+00:00",
                content=f"Post number {i}",
                tags="test",
            )

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Then: Should be limited to 200 posts
        self.assertEqual(len(items), 200)

    def test_rss_feed_ordered_by_most_recent(self):
        """Test that RSS feed items are ordered from most recent to oldest."""
        # Given: Posts with different timestamps

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Then: First item should be the most recent post
        first_item = items[0]
        first_guid = first_item.find('guid').text
        self.assertIn(self.post5.post_id, first_guid)  # Most recent

        # Last item should be the oldest post
        last_item = items[-1]
        last_guid = last_item.find('guid').text
        self.assertIn(self.post1.post_id, last_guid)  # Oldest

    def test_rss_feed_categories_from_tags(self):
        """Test that post tags are converted to RSS categories."""
        # Given: Post with multiple tags

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Find item for post3 (has multiple tags)
        post3_item = None
        for item in items:
            guid = item.find('guid').text
            if self.post3.post_id in guid:
                post3_item = item
                break

        self.assertIsNotNone(post3_item)

        # Then: Categories should match tags
        categories = [cat.text for cat in post3_item.findall('category')]
        expected_tags = self.post3.tags.split()
        self.assertEqual(set(categories), set(expected_tags))

    def test_rss_feed_guid_is_post_url(self):
        """Test that GUID is the post URL."""
        # Given: Posts exist

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Then: Each GUID should be feed#post_id format
        for item in items:
            guid = item.find('guid')
            self.assertIsNotNone(guid)
            self.assertIn('#', guid.text)
            self.assertTrue(guid.get('isPermaLink') in ['true', None])

    def test_rss_feed_content_type(self):
        """Test that RSS feed returns correct content type."""
        # Given: RSS endpoint

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Then: Content-Type should be application/rss+xml
        self.assertEqual(response['Content-Type'], 'application/rss+xml; charset=utf-8')

    def test_rss_feed_valid_xml(self):
        """Test that RSS feed returns valid XML."""
        # Given: RSS endpoint

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Then: Should be parseable as XML without errors
        try:
            ET.fromstring(response.content)
        except ET.ParseError as e:
            self.fail(f"RSS feed is not valid XML: {e}")

    def test_rss_feed_description_is_post_content(self):
        """Test that description contains the post content (converted to HTML)."""
        # Given: Posts with content

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Find item for post1
        post1_item = None
        for item in items:
            guid = item.find('guid').text
            if self.post1.post_id in guid:
                post1_item = item
                break

        self.assertIsNotNone(post1_item)

        # Then: Description should contain HTML-converted content
        description = post1_item.find('description')
        self.assertIsNotNone(description.text)
        # Content is now converted to HTML, so we check for HTML elements
        self.assertIn('<p>', description.text)
        # The original content should be present in the HTML
        self.assertIn('This post is about Emacs and org-mode', description.text)

    def test_rss_feed_author_is_nick(self):
        """Test that author is the profile nick."""
        # Given: Posts from different profiles

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Find item for post1
        post1_item = None
        for item in items:
            guid = item.find('guid').text
            if self.post1.post_id in guid:
                post1_item = item
                break

        self.assertIsNotNone(post1_item)

        # Then: Author should be the profile nick
        author = post1_item.find('author')
        self.assertIn(self.profile1.nick, author.text)

    def test_rss_feed_empty_when_no_posts(self):
        """Test RSS feed when there are no posts."""
        # Given: No posts exist
        Post.objects.all().delete()

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Then: Should still return valid RSS with no items
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Should have 0 items
        self.assertEqual(len(items), 0)

    def test_rss_feed_link_is_post_url(self):
        """Test that link element is the post URL."""
        # Given: Posts exist

        # When: We request the RSS feed
        response = self.client.get(self.rss_url)

        # Parse XML
        root = ET.fromstring(response.content)
        channel = root.find('channel')
        items = channel.findall('item')

        # Then: Each link should be feed#post_id format
        for item in items:
            link = item.find('link')
            guid = item.find('guid')
            # Link and GUID should be the same
            self.assertEqual(link.text, guid.text)
            self.assertIn('#', link.text)
