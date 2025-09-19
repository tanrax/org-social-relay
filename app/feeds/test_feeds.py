import json
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from .models import Feed


class FeedsViewTest(TestCase):
    """Test cases for the FeedsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.feeds_url = "/feeds/"  # Adjust based on your URL configuration

    def test_get_empty_feeds_list(self):
        """Test GET /feeds returns empty list when no feeds exist."""
        # Given: No feeds in the database
        Feed.objects.all().delete()

        # When: We request the feeds list
        response = self.client.get(self.feeds_url)

        # Then: We should get an empty list with success status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"], [])

    def test_get_feeds_list_with_data(self):
        """Test GET /feeds returns list of feeds when feeds exist."""
        # Given: Some feeds exist in the database
        Feed.objects.create(url="https://example.com/social.org")
        Feed.objects.create(url="https://test.dev/social.org")
        Feed.objects.create(url="https://demo.net/social.org")

        # When: We request the feeds list
        response = self.client.get(self.feeds_url)

        # Then: We should get all feeds with success status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 3)

        # Then: All feed URLs should be in the response
        feed_urls = response.data["data"]
        self.assertIn("https://example.com/social.org", feed_urls)
        self.assertIn("https://test.dev/social.org", feed_urls)
        self.assertIn("https://demo.net/social.org", feed_urls)

    def test_post_new_valid_feed_success(self):
        """Test POST /feeds creates a new valid feed successfully."""
        # Given: A new feed URL that is valid and accessible
        feed_url = "https://andros.dev/static/social.org"
        # Clean existing feed if any
        Feed.objects.filter(url=feed_url).delete()

        # When: We POST the new feed
        response = self.client.post(
            self.feeds_url,
            data=json.dumps({"feed": feed_url}),
            content_type="application/json",
        )

        # Then: We should get success response with 201 status
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"]["feed"], feed_url)

        # Then: The feed should be created in the database
        self.assertTrue(Feed.objects.filter(url=feed_url).exists())

    def test_post_existing_feed_returns_200(self):
        """Test POST /feeds returns 200 for existing feed without creating duplicate."""
        # Given: A feed that already exists
        feed_url = "https://existing.com/social.org"
        Feed.objects.create(url=feed_url)
        initial_count = Feed.objects.count()

        # When: We POST the same feed URL again
        response = self.client.post(
            self.feeds_url,
            data=json.dumps({"feed": feed_url}),
            content_type="application/json",
        )

        # Then: We should get success response with 200 status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"]["feed"], feed_url)

        # Then: No duplicate feed should be created
        self.assertEqual(Feed.objects.count(), initial_count)

    def test_post_feed_with_whitespace_handling(self):
        """Test POST /feeds handles whitespace in feed URLs correctly."""
        # Given: A valid feed URL with leading/trailing whitespace
        feed_url_with_spaces = "  https://andros.dev/static/social.org  "
        clean_feed_url = "https://andros.dev/static/social.org"
        # Clean existing feed if any
        Feed.objects.filter(url=clean_feed_url).delete()

        # When: We POST the feed with whitespace
        response = self.client.post(
            self.feeds_url,
            data=json.dumps({"feed": feed_url_with_spaces}),
            content_type="application/json",
        )

        # Then: We should get success response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["data"]["feed"], clean_feed_url)

        # Then: The feed should be stored without whitespace
        feed = Feed.objects.get(url=clean_feed_url)
        self.assertEqual(feed.url, clean_feed_url)

    def test_post_feed_missing_url_parameter(self):
        """Test POST /feeds returns error when feed URL is missing."""
        # Given: A request without feed parameter
        request_data = {}

        # When: We POST without feed parameter
        response = self.client.post(
            self.feeds_url,
            data=json.dumps(request_data),
            content_type="application/json",
        )

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertEqual(response.data["errors"], ["Feed URL is required"])
        self.assertIsNone(response.data["data"])

    def test_post_feed_empty_url_parameter(self):
        """Test POST /feeds returns error when feed URL is empty."""
        # Given: A request with empty feed parameter
        request_data = {"feed": ""}

        # When: We POST with empty feed parameter
        response = self.client.post(
            self.feeds_url,
            data=json.dumps(request_data),
            content_type="application/json",
        )

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertEqual(response.data["errors"], ["Feed URL is required"])
        self.assertIsNone(response.data["data"])

    def test_post_feed_whitespace_only_url(self):
        """Test POST /feeds returns error when feed URL contains only whitespace."""
        # Given: A request with whitespace-only feed parameter
        request_data = {"feed": "   "}

        # When: We POST with whitespace-only feed parameter
        response = self.client.post(
            self.feeds_url,
            data=json.dumps(request_data),
            content_type="application/json",
        )

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertEqual(response.data["errors"], ["Feed URL is required"])
        self.assertIsNone(response.data["data"])

    def test_post_feed_invalid_json(self):
        """Test POST /feeds handles invalid JSON gracefully."""
        # Given: Invalid JSON data
        invalid_json = '{"feed": "https://test.com/social.org"'  # Missing closing brace

        # When: We POST with invalid JSON
        response = self.client.post(
            self.feeds_url, data=invalid_json, content_type="application/json"
        )

        # Then: We should get a client error response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_feeds_response_format_compliance(self):
        """Test GET /feeds response format matches README specification."""
        # Given: Some feeds in the database
        Feed.objects.create(url="https://example.com/social.org")
        Feed.objects.create(url="https://another-example.com/social.org")

        # When: We request the feeds list
        response = self.client.get(self.feeds_url)

        # Then: Response should match exact README format
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertEqual(response.data["type"], "Success")
        self.assertIsInstance(response.data["errors"], list)
        self.assertIsInstance(response.data["data"], list)

    def test_post_feed_response_format_compliance(self):
        """Test POST /feeds response format matches README specification."""
        # Given: A valid feed URL
        feed_url = "https://rossabaker.com/social.org"
        # Clean existing feed if any
        Feed.objects.filter(url=feed_url).delete()

        # When: We POST the new feed
        response = self.client.post(
            self.feeds_url,
            data=json.dumps({"feed": feed_url}),
            content_type="application/json",
        )

        # Then: Response should match exact README format
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertEqual(response.data["type"], "Success")
        self.assertIsInstance(response.data["errors"], list)
        self.assertIsInstance(response.data["data"], dict)
        self.assertIn("feed", response.data["data"])

    def test_feeds_view_methods_allowed(self):
        """Test that only GET and POST methods are allowed on feeds endpoint."""
        # Given: The feeds endpoint

        # When: We try different HTTP methods
        put_response = self.client.put(self.feeds_url)
        delete_response = self.client.delete(self.feeds_url)
        patch_response = self.client.patch(self.feeds_url)

        # Then: Unsupported methods should return 405
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_post_invalid_feed_url_404(self):
        """Test POST /feeds returns error for invalid feed URL (404)."""
        # Given: A feed URL that returns 404
        feed_url = "https://example.com/nonexistent.org"

        # When: We POST the invalid feed
        response = self.client.post(
            self.feeds_url,
            data=json.dumps({"feed": feed_url}),
            content_type="application/json",
        )

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Invalid Org Social feed", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_post_invalid_feed_content(self):
        """Test POST /feeds returns error for URL with invalid content."""
        # Given: A URL that returns HTML instead of Org Social content
        feed_url = "https://www.google.com"

        # When: We POST the URL with invalid content
        response = self.client.post(
            self.feeds_url,
            data=json.dumps({"feed": feed_url}),
            content_type="application/json",
        )

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Invalid Org Social feed", response.data["errors"][0])
        self.assertIn("missing basic metadata", response.data["errors"][0])
        self.assertIsNone(response.data["data"])
