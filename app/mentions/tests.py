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

        # Create posts that mention profile1
        self.post_with_mention1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="This post mentions @example_user",
        )

        self.post_with_mention2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T14:00:00+00:00",
            content="Another mention of example_user",
        )

        # Create mention records
        Mention.objects.create(
            post=self.post_with_mention1,
            mentioned_profile=self.profile1,
            nickname="example_user",
        )

        Mention.objects.create(
            post=self.post_with_mention2,
            mentioned_profile=self.profile1,
            nickname="example_user",
        )

    def test_get_mentions_success(self):
        """Test GET /mentions/?feed=<feed_url> returns mentions for profile."""
        # Given: A profile with mentions exists
        feed_url = self.profile1.feed

        # When: We request mentions for the profile
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: We should get mentions successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain mention data as URLs
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)  # 2 mentions

        # Then: All data items should be strings (URLs)
        for mention_url in data:
            self.assertIsInstance(mention_url, str)
            self.assertIn("#", mention_url)  # Should contain the # separator

        # Then: Should contain expected mention URLs
        expected_url1 = f"{self.profile2.feed}#{self.post_with_mention1.post_id}"
        expected_url2 = f"{self.profile3.feed}#{self.post_with_mention2.post_id}"

        self.assertIn(expected_url1, data)
        self.assertIn(expected_url2, data)

        # Then: Meta should contain correct information
        meta = response.data["meta"]
        self.assertEqual(meta["feed"], feed_url)
        self.assertEqual(meta["total"], 2)
        self.assertIn("version", meta)

    def test_get_mentions_no_mentions(self):
        """Test GET /mentions/ returns empty array for profile with no mentions."""
        # Given: A profile with no mentions
        feed_url = self.profile2.feed

        # When: We request mentions for the profile
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: We should get empty array
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"], [])

        # Then: Meta should still be present
        meta = response.data["meta"]
        self.assertEqual(meta["feed"], feed_url)
        self.assertEqual(meta["total"], 0)
        self.assertIn("version", meta)

    def test_get_mentions_nonexistent_profile(self):
        """Test GET /mentions/ returns 404 for nonexistent profile."""
        # Given: A feed URL that doesn't exist
        nonexistent_feed = "https://nonexistent.com/social.org"

        # When: We request mentions for nonexistent profile
        response = self.client.get(self.mentions_url, {"feed": nonexistent_feed})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Profile not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_mentions_missing_parameters(self):
        """Test that missing required parameters return 400 error."""
        # Given: Mentions endpoint

        # When: We request without required parameters
        response = self.client.get(self.mentions_url)

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("required", response.data["errors"][0])

    def test_mentions_response_format_compliance(self):
        """Test mentions response format compliance with README specification."""
        # Given: A profile with mentions exists
        feed_url = self.profile1.feed

        # When: We request mentions
        response = self.client.get(self.mentions_url, {"feed": feed_url})

        # Then: Response should match expected format
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertIn("meta", response.data)
        self.assertEqual(response.data["type"], "Success")
        self.assertIsInstance(response.data["errors"], list)
        self.assertIsInstance(response.data["data"], list)
        self.assertIsInstance(response.data["meta"], dict)

    def test_mentions_view_methods_allowed(self):
        """Test that only GET method is allowed on mentions endpoint."""
        # Given: A valid mentions URL
        params = {"feed": self.profile1.feed}

        # When: We try different HTTP methods
        post_response = self.client.post(self.mentions_url, params)
        put_response = self.client.put(self.mentions_url, params)
        delete_response = self.client.delete(self.mentions_url, params)
        patch_response = self.client.patch(self.mentions_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)