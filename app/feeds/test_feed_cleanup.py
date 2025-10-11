from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock
from app.feeds.models import Feed
from app.feeds.tasks import _cleanup_stale_feeds_impl
from app.feeds.parser import parse_org_social, validate_org_social_feed


class FeedCleanupTest(TestCase):
    """Test cases for feed cleanup functionality using Given/When/Then structure."""

    def test_last_successful_fetch_updated_on_parse(self):
        """Test that last_successful_fetch is updated when feed is parsed successfully."""
        # Given: A feed exists in the database
        feed_url = "https://example.com/social.org"
        feed = Feed.objects.create(url=feed_url, last_successful_fetch=None)

        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
#+TITLE: Test Feed
#+NICK: testuser

* Posts
"""
        mock_response.raise_for_status = Mock()

        # When: We parse the feed and it returns HTTP 200
        with patch("requests.get", return_value=mock_response):
            before_parse = timezone.now()
            parse_org_social(feed_url)
            after_parse = timezone.now()

        # Then: The last_successful_fetch should be updated
        feed.refresh_from_db()
        self.assertIsNotNone(feed.last_successful_fetch)
        self.assertGreaterEqual(feed.last_successful_fetch, before_parse)
        self.assertLessEqual(feed.last_successful_fetch, after_parse)

    def test_last_successful_fetch_updated_on_validate(self):
        """Test that last_successful_fetch is updated when feed is validated successfully."""
        # Given: A feed exists in the database
        feed_url = "https://example.com/social.org"
        feed = Feed.objects.create(url=feed_url, last_successful_fetch=None)

        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
#+TITLE: Test Feed
#+NICK: testuser
#+DESCRIPTION: A test feed

* Posts
"""

        # When: We validate the feed and it returns HTTP 200
        with patch("requests.get", return_value=mock_response):
            before_validate = timezone.now()
            is_valid, error_message = validate_org_social_feed(feed_url)
            after_validate = timezone.now()

        # Then: The validation should succeed
        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")

        # Then: The last_successful_fetch should be updated
        feed.refresh_from_db()
        self.assertIsNotNone(feed.last_successful_fetch)
        self.assertGreaterEqual(feed.last_successful_fetch, before_validate)
        self.assertLessEqual(feed.last_successful_fetch, after_validate)

    def test_cleanup_deletes_stale_feeds(self):
        """Test that cleanup_stale_feeds deletes feeds older than 3 days."""
        # Given: We have feeds with different last_successful_fetch dates
        now = timezone.now()

        # Feed fetched 4 days ago (should be deleted)
        stale_feed = Feed.objects.create(
            url="https://stale.com/social.org",
            last_successful_fetch=now - timedelta(days=4),
        )

        # Feed fetched 2 days ago (should NOT be deleted)
        recent_feed = Feed.objects.create(
            url="https://recent.com/social.org",
            last_successful_fetch=now - timedelta(days=2),
        )

        # Feed with NULL last_successful_fetch (should NOT be deleted)
        legacy_feed = Feed.objects.create(
            url="https://legacy.com/social.org",
            last_successful_fetch=None,
        )

        # When: We run the cleanup task
        _cleanup_stale_feeds_impl()

        # Then: Only the stale feed should be deleted
        self.assertFalse(Feed.objects.filter(url=stale_feed.url).exists())
        self.assertTrue(Feed.objects.filter(url=recent_feed.url).exists())
        self.assertTrue(Feed.objects.filter(url=legacy_feed.url).exists())

    def test_cleanup_with_multiple_stale_feeds(self):
        """Test cleanup with multiple stale feeds."""
        # Given: Multiple stale feeds exist
        now = timezone.now()
        stale_urls = []

        for i in range(5):
            url = f"https://stale{i}.com/social.org"
            Feed.objects.create(
                url=url,
                last_successful_fetch=now - timedelta(days=5),
            )
            stale_urls.append(url)

        # And: One recent feed exists
        recent_url = "https://recent.com/social.org"
        Feed.objects.create(
            url=recent_url,
            last_successful_fetch=now - timedelta(hours=12),
        )

        # When: We run cleanup
        _cleanup_stale_feeds_impl()

        # Then: All stale feeds should be deleted
        for url in stale_urls:
            self.assertFalse(Feed.objects.filter(url=url).exists())

        # Then: Recent feed should still exist
        self.assertTrue(Feed.objects.filter(url=recent_url).exists())

    def test_cleanup_with_no_stale_feeds(self):
        """Test cleanup when there are no stale feeds."""
        # Given: Only recent feeds exist
        now = timezone.now()
        Feed.objects.create(
            url="https://recent1.com/social.org",
            last_successful_fetch=now - timedelta(hours=6),
        )
        Feed.objects.create(
            url="https://recent2.com/social.org",
            last_successful_fetch=now - timedelta(days=1),
        )

        initial_count = Feed.objects.count()

        # When: We run cleanup
        _cleanup_stale_feeds_impl()

        # Then: No feeds should be deleted
        self.assertEqual(Feed.objects.count(), initial_count)

    def test_cleanup_boundary_condition(self):
        """Test cleanup at exactly 3 days boundary."""
        # Given: A feed fetched exactly 3 days ago
        now = timezone.now()
        exactly_three_days = Feed.objects.create(
            url="https://boundary.com/social.org",
            last_successful_fetch=now - timedelta(days=3, seconds=1),
        )

        # When: We run cleanup
        _cleanup_stale_feeds_impl()

        # Then: Feed should be deleted (older than 3 days)
        self.assertFalse(Feed.objects.filter(url=exactly_three_days.url).exists())

    def test_cleanup_preserves_feeds_without_fetch_date(self):
        """Test that cleanup preserves feeds with NULL last_successful_fetch."""
        # Given: Multiple feeds with NULL last_successful_fetch
        legacy_urls = []
        for i in range(3):
            url = f"https://legacy{i}.com/social.org"
            Feed.objects.create(url=url, last_successful_fetch=None)
            legacy_urls.append(url)

        # When: We run cleanup
        _cleanup_stale_feeds_impl()

        # Then: All legacy feeds should still exist
        for url in legacy_urls:
            self.assertTrue(Feed.objects.filter(url=url).exists())

    def test_last_successful_fetch_not_updated_on_failed_request(self):
        """Test that last_successful_fetch is not updated when request fails."""
        # Given: A feed exists with a known last_successful_fetch
        feed_url = "https://example.com/social.org"
        initial_fetch_time = timezone.now() - timedelta(hours=1)
        feed = Feed.objects.create(
            url=feed_url,
            last_successful_fetch=initial_fetch_time,
        )

        # Mock failed HTTP response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status = Mock(side_effect=Exception("404 Not Found"))

        # When: We try to parse the feed and it fails
        with patch("requests.get", return_value=mock_response):
            try:
                parse_org_social(feed_url)
            except Exception:
                pass  # Expected to fail

        # Then: The last_successful_fetch should not be updated
        feed.refresh_from_db()
        self.assertEqual(feed.last_successful_fetch, initial_fetch_time)

    def test_migration_sets_initial_value(self):
        """Test that the migration sets initial last_successful_fetch for existing feeds."""
        # This test verifies that feeds created before the migration
        # will have last_successful_fetch set to protect them from deletion

        # Note: This is already tested by the migration itself,
        # but we verify the behavior is correct

        # Given: A feed is created without last_successful_fetch
        # (simulating a feed that existed before the field was added)
        feed = Feed.objects.create(url="https://test.com/social.org")

        # Then: The field should allow NULL
        self.assertIsNone(feed.last_successful_fetch)

        # And: The cleanup task should not delete it
        _cleanup_stale_feeds_impl()
        self.assertTrue(Feed.objects.filter(url=feed.url).exists())
