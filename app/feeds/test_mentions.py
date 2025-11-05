from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from app.feeds.models import Profile, Post, Mention


class MentionsViewTest(TestCase):
    """Test cases for the MentionsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.mentions_url = "/mentions/"

        # Create test profiles
        self.profile1 = Profile.objects.create(
            feed="https://alice.example.com/social.org",
            title="Alice Smith",
            nick="alice",
            description="Alice's profile",
        )

        self.profile2 = Profile.objects.create(
            feed="https://bob.example.com/social.org",
            title="Bob Johnson",
            nick="bob",
            description="Bob's profile",
        )

        self.profile3 = Profile.objects.create(
            feed="https://charlie.example.com/social.org",
            title="Charlie Brown",
            nick="charlie",
            description="Charlie's profile",
        )

        # Create test posts
        self.post1 = Post.objects.create(
            profile=self.profile2,
            post_id="2024-01-01T10:00:00Z",
            content="Hello @alice, how are you doing?",
        )

        self.post2 = Post.objects.create(
            profile=self.profile3,
            post_id="2024-01-01T11:00:00Z",
            content="Hey @alice, check this out!",
        )

        # Create test mentions
        self.mention1 = Mention.objects.create(
            post=self.post1,
            mentioned_profile=self.profile1,
            nickname="alice",
        )

        self.mention2 = Mention.objects.create(
            post=self.post2,
            mentioned_profile=self.profile1,
            nickname="alice",
        )

    def test_get_mentions_success(self):
        """Test GET /mentions returns mentions for a specific feed."""
        # Given: A profile with mentions
        feed_url = "https://alice.example.com/social.org"

        # When: We request mentions for this feed
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: We should get all mentions for this profile
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 2)

        # Then: Check mention data structure (should be URLs only)
        mentions = response.data["data"]
        self.assertIsInstance(mentions, list)
        self.assertEqual(len(mentions), 2)

        # Then: Check that data contains post URLs
        for mention_url in mentions:
            self.assertIsInstance(mention_url, str)
            self.assertIn("#", mention_url)  # Should contain post ID after #

        # Then: Check meta field exists and has required structure
        self.assertIn("meta", response.data)
        meta = response.data["meta"]
        self.assertIn("feed", meta)
        self.assertIn("total", meta)
        self.assertEqual(meta["feed"], "https://alice.example.com/social.org")
        self.assertEqual(meta["total"], 2)

        # Then: Should have ETag and Last-Modified headers
        self.assertIn("ETag", response)
        self.assertIn("Last-Modified", response)

    def test_get_mentions_missing_feed_parameter(self):
        """Test GET /mentions returns error when feed parameter is missing."""
        # Given: A request without feed parameter

        # When: We request mentions without feed parameter
        response = self.client.get(self.mentions_url)

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertEqual(response.data["errors"], ["Feed URL parameter is required"])
        self.assertIsNone(response.data["data"])

    def test_get_mentions_empty_feed_parameter(self):
        """Test GET /mentions returns error when feed parameter is empty."""
        # Given: A request with empty feed parameter
        feed_url = ""

        # When: We request mentions with empty feed parameter
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertEqual(response.data["errors"], ["Feed URL parameter is required"])
        self.assertIsNone(response.data["data"])

    def test_get_mentions_whitespace_feed_parameter(self):
        """Test GET /mentions returns error when feed parameter is only whitespace."""
        # Given: A request with whitespace-only feed parameter
        feed_url = "   "

        # When: We request mentions with whitespace-only feed parameter
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: We should get error response with 400 status
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertEqual(response.data["errors"], ["Feed URL parameter is required"])
        self.assertIsNone(response.data["data"])

    def test_get_mentions_profile_not_found(self):
        """Test GET /mentions returns error when profile doesn't exist."""
        # Given: A feed URL that doesn't exist in our database
        feed_url = "https://nonexistent.example.com/social.org"

        # When: We request mentions for this non-existent feed
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: We should get error response with 404 status
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertEqual(
            response.data["errors"], ["Profile not found for the given feed URL"]
        )
        self.assertIsNone(response.data["data"])

    def test_get_mentions_no_mentions(self):
        """Test GET /mentions returns empty list when profile has no mentions."""
        # Given: A profile with no mentions
        feed_url = "https://bob.example.com/social.org"

        # When: We request mentions for this profile
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: We should get empty list with success status
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"], [])

    def test_mentions_response_format_compliance(self):
        """Test GET /mentions response format compliance."""
        # Given: A profile with mentions
        feed_url = "https://alice.example.com/social.org"

        # When: We request mentions for this feed
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: Response should match expected format
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertEqual(response.data["type"], "Success")
        self.assertIsInstance(response.data["errors"], list)
        self.assertIsInstance(response.data["data"], list)

        # Then: Each mention should be a URL string
        for mention in response.data["data"]:
            self.assertIsInstance(mention, str)
            self.assertIn("#", mention)  # Should contain post ID after #

        # Then: Check meta field
        self.assertIn("meta", response.data)
        meta = response.data["meta"]
        self.assertIn("feed", meta)
        self.assertIn("total", meta)

        # Then: Should have ETag and Last-Modified headers
        self.assertIn("ETag", response)
        self.assertIn("Last-Modified", response)

    def test_mentions_view_only_get_allowed(self):
        """Test that only GET method is allowed on mentions endpoint."""
        # Given: The mentions endpoint
        feed_url = "https://alice.example.com/social.org"

        # When: We try different HTTP methods
        post_response = self.client.post(self.mentions_url, {"feed": feed_url})
        put_response = self.client.put(self.mentions_url, {"feed": feed_url})
        delete_response = self.client.delete(self.mentions_url, {"feed": feed_url})
        patch_response = self.client.patch(self.mentions_url, {"feed": feed_url})

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_get_mentions_with_whitespace_handling(self):
        """Test GET /mentions handles whitespace in feed URLs correctly."""
        # Given: A valid feed URL with leading/trailing whitespace
        feed_url_with_spaces = "  https://alice.example.com/social.org  "

        # When: We request mentions with whitespace
        response = self.client.get(self.mentions_url, {"feed": feed_url_with_spaces})

        # Then: We should get success response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(len(response.data["data"]), 2)

    def test_mentions_ordering_most_recent_first(self):
        """Test that mentions are ordered from most recent to oldest."""
        # Given: A profile with multiple mentions created at different times
        import time

        # Create an additional profile and posts with specific timestamps
        profile4 = Profile.objects.create(
            feed="https://david.example.com/social.org",
            title="David Wilson",
            nick="david",
            description="David's profile",
        )

        # Create posts with different timestamps
        post3 = Post.objects.create(
            profile=profile4,
            post_id="2024-01-01T08:00:00Z",
            content="Early mention of @alice",
        )

        post4 = Post.objects.create(
            profile=profile4,
            post_id="2024-01-01T12:00:00Z",
            content="Later mention of @alice",
        )

        # Create mentions with specific creation times
        # Note: Since we can't control created_at directly, we'll create them in order
        # and rely on the database's auto-timestamp behavior
        Mention.objects.create(
            post=post3,
            mentioned_profile=self.profile1,
            nickname="alice",
        )

        # Add a small delay to ensure different timestamps
        time.sleep(0.01)

        Mention.objects.create(
            post=post4,
            mentioned_profile=self.profile1,
            nickname="alice",
        )

        # When: We request mentions for alice
        response = self.client.get(
            self.mentions_url, {"feed": "https://alice.example.com/social.org"}
        )

        # Then: We should get mentions in reverse chronological order (newest first)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mentions_urls = response.data["data"]

        # Should have 4 mentions total (2 from setUp + 2 new ones)
        self.assertEqual(len(mentions_urls), 4)

        # The most recent post should be first (based on post timestamp, not mention creation time)
        # post4 has timestamp 12:00:00 which is later than post3 (08:00:00)
        first_mention_url = mentions_urls[0]
        self.assertIn(
            "2024-01-01T12:00:00Z", first_mention_url
        )  # post4 timestamp (later in day)

        # Verify all URLs are properly formatted
        for url in mentions_urls:
            self.assertIn("https://", url)
            self.assertIn("#", url)
