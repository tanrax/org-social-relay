from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch, Mock
from app.feeds.models import Profile
import requests


class FeedContentViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create test profile
        self.profile = Profile.objects.create(
            feed="https://example.com/social.org",
            title="Test Profile",
            nick="testuser",
        )

    def test_get_feed_content_success(self):
        """Test successfully fetching feed content"""
        mock_content = """#+TITLE: My Social Feed
#+AUTHOR: John Doe

* 2025-02-05T10:00:00+0100
:PROPERTIES:
:ID: 2025-02-05T10:00:00+0100
:END:

Hello, world! This is my first post.
"""

        with patch("app.feedcontent.views.requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = mock_content.encode("utf-8")
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            response = self.client.get(
                "/feed-content/", {"feed": "https://example.com/social.org"}
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["type"], "Success")
            self.assertEqual(response.data["data"]["content"], mock_content)
            self.assertIn("_links", response.data)
            self.assertIn("self", response.data["_links"])

    def test_get_feed_content_missing_parameter(self):
        """Test error when feed parameter is missing"""
        response = self.client.get("/feed-content/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Feed URL parameter is required", response.data["errors"])

    def test_get_feed_content_empty_parameter(self):
        """Test error when feed parameter is empty"""
        response = self.client.get("/feed-content/", {"feed": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Feed URL parameter is required", response.data["errors"])

    def test_get_feed_content_feed_not_found(self):
        """Test error when feed is not registered in relay"""
        response = self.client.get(
            "/feed-content/", {"feed": "https://unknown.com/social.org"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Feed not found in relay", response.data["errors"])

    def test_get_feed_content_timeout(self):
        """Test error when feed server times out"""
        with patch("app.feedcontent.views.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()

            response = self.client.get(
                "/feed-content/", {"feed": "https://example.com/social.org"}
            )

            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.data["type"], "Error")
            self.assertIn("Request timeout", response.data["errors"][0])

    def test_get_feed_content_connection_error(self):
        """Test error when connection to feed server fails"""
        with patch("app.feedcontent.views.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()

            response = self.client.get(
                "/feed-content/", {"feed": "https://example.com/social.org"}
            )

            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.data["type"], "Error")
            self.assertIn("Connection error", response.data["errors"][0])

    def test_get_feed_content_http_error(self):
        """Test error when feed server returns HTTP error"""
        with patch("app.feedcontent.views.requests.get") as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "404 Not Found"
            )
            mock_get.return_value = mock_response

            response = self.client.get(
                "/feed-content/", {"feed": "https://example.com/social.org"}
            )

            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.data["type"], "Error")
            self.assertIn("HTTP error", response.data["errors"][0])

    def test_get_feed_content_unicode(self):
        """Test fetching feed content with unicode characters"""
        mock_content = """#+TITLE: Mi Feed Social
#+AUTHOR: José García

* 2025-02-05T10:00:00+0100
:PROPERTIES:
:ID: 2025-02-05T10:00:00+0100
:END:

¡Hola mundo! Este es mi primer post con émojis 🚀 ❤️
"""

        with patch("app.feedcontent.views.requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = mock_content.encode("utf-8")
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            response = self.client.get(
                "/feed-content/", {"feed": "https://example.com/social.org"}
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["type"], "Success")
            self.assertEqual(response.data["data"]["content"], mock_content)
            self.assertIn("🚀", response.data["data"]["content"])
            self.assertIn("❤️", response.data["data"]["content"])

    def test_get_feed_content_preserves_formatting(self):
        """Test that feed content preserves whitespace and formatting"""
        mock_content = """#+TITLE: Test Feed

* 2025-02-05T10:00:00+0100
:PROPERTIES:
:ID: 2025-02-05T10:00:00+0100
:END:

Line 1

Line 2 with    multiple   spaces
	Line 3 with tab
"""

        with patch("app.feedcontent.views.requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = mock_content.encode("utf-8")
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            response = self.client.get(
                "/feed-content/", {"feed": "https://example.com/social.org"}
            )

            self.assertEqual(response.status_code, 200)
            # Content should be exactly as provided, preserving all whitespace
            self.assertEqual(response.data["data"]["content"], mock_content)
