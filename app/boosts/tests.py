from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post


class BoostsViewTest(TestCase):
    """Test cases for the BoostsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.boosts_url = "/boosts/"

        # Create test profiles
        self.profile1 = Profile.objects.create(
            feed="https://example.com/social.org",
            title="Example Profile",
            nick="example_user",
            description="Test profile 1",
        )
        self.profile2 = Profile.objects.create(
            feed="https://alice.com/social.org",
            title="Alice Profile",
            nick="alice",
            description="Alice's profile",
        )
        self.profile3 = Profile.objects.create(
            feed="https://bob.com/social.org",
            title="Bob Profile",
            nick="bob",
            description="Bob's profile",
        )
        self.profile4 = Profile.objects.create(
            feed="https://charlie.com/social.org",
            title="Charlie Profile",
            nick="charlie",
            description="Charlie's profile",
        )

        # Create original post
        self.original_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-02-05T10:00:00+0100",
            content="This is an amazing discovery!",
        )

        # Create boosts of the original post
        self.boost1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-02-05T14:00:00+0100",
            content="Guys, you have to see this!",
            include=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        self.boost2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-02-05T15:30:00+0100",
            content="",  # Simple boost without comment
            include=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        self.boost3 = Post.objects.create(
            profile=self.profile4,
            post_id="2025-02-05T16:45:00+0100",
            content="",  # Another simple boost
            include=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        # Create another post without boosts
        self.post_without_boosts = Post.objects.create(
            profile=self.profile1,
            post_id="2025-02-05T11:00:00+0100",
            content="Another post without boosts",
        )

        # Create a post that boosts a different post
        self.other_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-02-05T09:00:00+0100",
            content="Different post",
        )

        self.boost_other = Post.objects.create(
            profile=self.profile3,
            post_id="2025-02-05T17:00:00+0100",
            content="Boosting different post",
            include=f"{self.profile2.feed}#{self.other_post.post_id}",
        )

    def test_get_boosts_success(self):
        """Test GET /boosts/?post=<post_url> returns list of boosts."""
        # Given: A post with boosts exists
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request boosts for the post
        response = self.client.get(self.boosts_url, {"post": post_url})

        # Then: We should get boosts successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain list of boost post URLs
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)  # 3 boosts

        # Then: Boosts should be ordered by post_id (most recent first)
        expected_boosts = [
            f"{self.profile4.feed}#{self.boost3.post_id}",
            f"{self.profile3.feed}#{self.boost2.post_id}",
            f"{self.profile2.feed}#{self.boost1.post_id}",
        ]
        self.assertEqual(data, expected_boosts)

        # Then: Meta should contain post URL and total count
        meta = response.data["meta"]
        self.assertEqual(meta["post"], post_url)
        self.assertEqual(meta["total"], 3)

        # Then: Links should contain self reference
        links = response.data["_links"]
        self.assertIn("self", links)
        self.assertIn("/boosts/", links["self"]["href"])

    def test_get_boosts_no_boosts(self):
        """Test GET /boosts/?post=<post_url> when post has no boosts."""
        # Given: A post without boosts exists
        post_url = f"{self.profile1.feed}#{self.post_without_boosts.post_id}"

        # When: We request boosts for the post
        response = self.client.get(self.boosts_url, {"post": post_url})

        # Then: We should get successful response with empty list
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        data = response.data["data"]
        self.assertEqual(len(data), 0)
        self.assertEqual(response.data["meta"]["total"], 0)

    def test_get_boosts_missing_post_parameter(self):
        """Test GET /boosts/ without post parameter returns error."""
        # Given: No post parameter provided

        # When: We request boosts without post parameter
        response = self.client.get(self.boosts_url)

        # Then: We should get a 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("'post' parameter is required", response.data["errors"])

    def test_get_boosts_invalid_post_url_format(self):
        """Test GET /boosts/?post=<invalid_url> returns error."""
        # Given: An invalid post URL (missing #)
        invalid_url = "https://example.com/social.org"

        # When: We request boosts with invalid URL
        response = self.client.get(self.boosts_url, {"post": invalid_url})

        # Then: We should get a 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Invalid post URL format", response.data["errors"][0])

    def test_get_boosts_post_not_found(self):
        """Test GET /boosts/?post=<nonexistent_post> returns 404."""
        # Given: A non-existent post URL
        post_url = "https://nonexistent.com/social.org#2025-01-01T00:00:00+00:00"

        # When: We request boosts for non-existent post
        response = self.client.get(self.boosts_url, {"post": post_url})

        # Then: We should get a 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Post not found", response.data["errors"])

    def test_get_boosts_profile_not_found(self):
        """Test GET /boosts/?post=<url_with_unknown_profile> returns 404."""
        # Given: A URL with unknown profile
        post_url = "https://unknown-profile.com/social.org#2025-01-01T00:00:00+00:00"

        # When: We request boosts
        response = self.client.get(self.boosts_url, {"post": post_url})

        # Then: We should get a 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Post not found", response.data["errors"])

    def test_boosts_isolated_by_post(self):
        """Test that boosts are correctly isolated by post."""
        # Given: Multiple posts with boosts exist
        post1_url = f"{self.profile1.feed}#{self.original_post.post_id}"
        post2_url = f"{self.profile2.feed}#{self.other_post.post_id}"

        # When: We request boosts for post 1
        response1 = self.client.get(self.boosts_url, {"post": post1_url})

        # Then: We should only get boosts for post 1
        self.assertEqual(len(response1.data["data"]), 3)

        # When: We request boosts for post 2
        response2 = self.client.get(self.boosts_url, {"post": post2_url})

        # Then: We should only get boosts for post 2
        self.assertEqual(len(response2.data["data"]), 1)
        self.assertIn(
            f"{self.profile3.feed}#{self.boost_other.post_id}",
            response2.data["data"],
        )

    def test_boosts_caching(self):
        """Test that boosts responses are cached."""
        # Given: A post with boosts
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request boosts twice
        response1 = self.client.get(self.boosts_url, {"post": post_url})
        response2 = self.client.get(self.boosts_url, {"post": post_url})

        # Then: Both responses should be identical
        self.assertEqual(response1.data, response2.data)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
