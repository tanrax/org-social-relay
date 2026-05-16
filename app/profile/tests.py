from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Follow, Profile


class ProfileViewTest(TestCase):
    """Test cases for the ProfileView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.url = "/profile/"

        self.profile_main = Profile.objects.create(
            feed="https://example.com/social.org",
            title="Example Profile",
            nick="example_user",
        )
        self.profile_alice = Profile.objects.create(
            feed="https://alice.org/social.org",
            title="Alice",
            nick="alice",
        )
        self.profile_bob = Profile.objects.create(
            feed="https://bob.org/social.org",
            title="Bob",
            nick="bob",
        )
        self.profile_carol = Profile.objects.create(
            feed="https://carol.org/social.org",
            title="Carol",
            nick="carol",
        )

        Follow.objects.create(follower=self.profile_alice, followed=self.profile_main)
        Follow.objects.create(follower=self.profile_bob, followed=self.profile_main)

    def test_get_profile_with_followers(self):
        """Test GET /profile/?feed=<url> returns correct followers list."""
        # Given: A profile followed by two users
        feed_url = self.profile_main.feed

        # When: We request the profile
        response = self.client.get(self.url, {"feed": feed_url})

        # Then: Response is successful
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Data contains feed and followers
        data = response.data["data"]
        self.assertEqual(data["feed"], feed_url)
        self.assertIsInstance(data["followers"], list)
        self.assertIn(self.profile_alice.feed, data["followers"])
        self.assertIn(self.profile_bob.feed, data["followers"])
        self.assertNotIn(self.profile_carol.feed, data["followers"])

        # Then: Meta contains correct counts
        meta = response.data["meta"]
        self.assertEqual(meta["feed"], feed_url)
        self.assertEqual(meta["total_followers"], 2)

    def test_get_profile_no_followers(self):
        """Test GET /profile/ returns empty followers for profile with no followers."""
        # Given: A profile with no followers
        feed_url = self.profile_carol.feed

        # When: We request the profile
        response = self.client.get(self.url, {"feed": feed_url})

        # Then: Response is successful with empty followers
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["data"]["followers"], [])
        self.assertEqual(response.data["meta"]["total_followers"], 0)

    def test_get_profile_not_found(self):
        """Test GET /profile/ returns 404 for non-existent feed."""
        # Given: A feed URL not registered in the relay
        nonexistent_feed = "https://nonexistent.com/social.org"

        # When: We request the profile
        response = self.client.get(self.url, {"feed": nonexistent_feed})

        # Then: We get 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Profile not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_get_profile_missing_feed_param(self):
        """Test GET /profile/ returns 400 when feed param is missing."""
        # When: We request without the feed parameter
        response = self.client.get(self.url)

        # Then: We get 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("required", response.data["errors"][0])

    def test_get_profile_response_format(self):
        """Test GET /profile/ response matches README specification."""
        # Given: A registered profile
        feed_url = self.profile_main.feed

        # When: We request the profile
        response = self.client.get(self.url, {"feed": feed_url})

        # Then: Response keys are correct
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertIn("meta", response.data)
        self.assertIn("_links", response.data)

        data = response.data["data"]
        self.assertIn("feed", data)
        self.assertIn("followers", data)

        meta = response.data["meta"]
        self.assertIn("feed", meta)
        self.assertIn("total_followers", meta)

        links = response.data["_links"]
        self.assertIn("self", links)
        self.assertIn("href", links["self"])
        self.assertIn("method", links["self"])
        self.assertEqual(links["self"]["method"], "GET")

    def test_get_profile_self_link_encoded(self):
        """Test that the self link URL-encodes the feed parameter."""
        # Given: A feed URL with special characters
        feed_url = self.profile_main.feed

        # When: We request the profile
        response = self.client.get(self.url, {"feed": feed_url})

        # Then: Self link is URL-encoded
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        href = response.data["_links"]["self"]["href"]
        self.assertIn("%3A", href)  # : is encoded
        self.assertIn("%2F", href)  # / is encoded

    def test_get_profile_http_methods(self):
        """Test that only GET is allowed on the profile endpoint."""
        # Given: A valid feed URL
        params = {"feed": self.profile_main.feed}

        # When/Then: Non-GET methods return 405
        self.assertEqual(
            self.client.post(self.url, params).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.put(self.url, params).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(self.url, params).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_get_profile_followers_are_feeds_only(self):
        """Test that followers list contains only feed URLs, not profile metadata."""
        # Given: A profile with a follower
        feed_url = self.profile_main.feed

        # When: We request the profile
        response = self.client.get(self.url, {"feed": feed_url})

        # Then: Each follower entry is a plain URL string
        for follower in response.data["data"]["followers"]:
            self.assertIsInstance(follower, str)
            self.assertTrue(follower.startswith("http"))
