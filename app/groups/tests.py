from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post


class GroupsViewTest(TestCase):
    """Test cases for the GroupsView API."""

    def setUp(self):
        self.client = APIClient()
        self.groups_url = "/groups/"

    @override_settings(ENABLED_GROUPS=[], GROUPS_MAP={})
    def test_no_groups_configured(self):
        """Test GET /groups/ when no groups are configured."""
        # Given: No groups configured

        # When: We request groups list
        response = self.client.get(self.groups_url)

        # Then: Should return 404 with error message
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("No groups configured", response.data["errors"][0])

    @override_settings(
        ENABLED_GROUPS=["emacs", "org-social", "python"],
        GROUPS_MAP={"emacs": "Emacs", "org-social": "Org Social", "python": "Python"},
    )
    def test_list_groups_success(self):
        """Test GET /groups/ returns configured groups."""
        # Given: Groups configured

        # When: We request groups list
        response = self.client.get(self.groups_url)

        # Then: Should return success with group display names
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(len(response.data["data"]), 3)
        # Data should contain display names, not slugs
        self.assertIn("Emacs", response.data["data"])
        self.assertIn("Org Social", response.data["data"])
        self.assertIn("Python", response.data["data"])

    @override_settings(
        ENABLED_GROUPS=["emacs", "org-social"],
        GROUPS_MAP={"emacs": "Emacs", "org-social": "Org Social"},
    )
    def test_list_groups_empty_groups(self):
        """Test GET /groups/ when groups are configured."""
        # Given: Groups configured

        # When: We request groups list
        response = self.client.get(self.groups_url)

        # Then: Should return group display names
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(len(response.data["data"]), 2)
        self.assertIn("Emacs", response.data["data"])
        self.assertIn("Org Social", response.data["data"])


class GroupMessagesViewTest(TestCase):
    """Test cases for the GroupMessagesView API."""

    def setUp(self):
        self.client = APIClient()

        # Create test profiles
        self.profile1 = Profile.objects.create(
            feed="https://example.com/social.org", nick="user1"
        )
        self.profile2 = Profile.objects.create(
            feed="https://test.com/social.org", nick="user2"
        )

    @override_settings(
        ENABLED_GROUPS=["emacs", "python"],
        GROUPS_MAP={"emacs": "Emacs", "python": "Python"},
    )
    def test_get_group_messages_success(self):
        """Test GET /groups/{id}/ returns group messages."""
        # Given: Posts with group metadata (using slugs)
        Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="First emacs post",
            group="emacs",
        )
        Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="Second emacs post",
            group="emacs",
        )
        # Post from non-emacs group (should not appear)
        other_profile = Profile.objects.create(
            feed="https://other.com/social.org", nick="other"
        )
        Post.objects.create(
            profile=other_profile,
            post_id="2025-01-01T14:00:00+00:00",
            content="Other post",
            group="python",
        )

        # When: We request emacs group messages (using slug in URL)
        response = self.client.get("/groups/emacs/")

        # Then: Should return only emacs posts
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(len(response.data["data"]), 2)

        # Check meta - should contain display name, not slug
        self.assertEqual(response.data["meta"]["group"], "Emacs")
        self.assertIn("members", response.data["meta"])

        # Then: Should have ETag and Last-Modified headers
        self.assertIn("ETag", response)
        self.assertIn("Last-Modified", response)

    @override_settings(ENABLED_GROUPS=["emacs"], GROUPS_MAP={"emacs": "Emacs"})
    def test_get_group_messages_with_replies(self):
        """Test group messages with reply tree structure."""
        # Given: Posts with replies in group
        post1 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="Original post",
            group="emacs",
        )
        Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="Reply to post1",
            reply_to=f"{self.profile1.feed}#{post1.post_id}",
            group="emacs",
        )

        # When: We request group messages
        response = self.client.get("/groups/emacs/")

        # Then: Should return tree structure
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        # Find the original post
        original = None
        for msg in data:
            if "2025-01-01T12:00:00" in msg["post"]:
                original = msg
                break

        self.assertIsNotNone(original)
        # Check if reply is in children
        self.assertEqual(len(original["children"]), 1)
        self.assertIn("2025-01-01T13:00:00", original["children"][0]["post"])

    @override_settings(ENABLED_GROUPS=["emacs"], GROUPS_MAP={"emacs": "Emacs"})
    def test_get_group_messages_empty(self):
        """Test group with no messages."""
        # Given: No posts in group

        # When: We request group messages
        response = self.client.get("/groups/emacs/")

        # Then: Should return empty data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["data"], [])
        self.assertEqual(len(response.data["data"]), 0)

    @override_settings(ENABLED_GROUPS=["emacs"], GROUPS_MAP={"emacs": "Emacs"})
    def test_get_group_messages_invalid_group(self):
        """Test getting messages from invalid group."""
        # Given: Invalid group ID

        # When: We request invalid group
        response = self.client.get("/groups/invalid-group/")

        # Then: Should return 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")

    @override_settings(
        ENABLED_GROUPS=["emacs", "python"],
        GROUPS_MAP={"emacs": "Emacs", "python": "Python"},
    )
    def test_get_group_messages_caching(self):
        """Test that group messages are cached."""
        # Given: Posts in group
        Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="Test post",
            group="emacs",
        )

        # When: We request group messages twice
        response1 = self.client.get("/groups/emacs/")
        response2 = self.client.get("/groups/emacs/")

        # Then: Both should succeed
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # And ETag should be the same (indicating cache hit)
        self.assertEqual(response1["ETag"], response2["ETag"])


class GroupsIntegrationTest(TestCase):
    """Integration tests for groups functionality."""

    def setUp(self):
        self.client = APIClient()

    @override_settings(
        ENABLED_GROUPS=["emacs", "org-social", "python"],
        GROUPS_MAP={"emacs": "Emacs", "org-social": "Org Social", "python": "Python"},
    )
    def test_full_group_workflow(self):
        """Test complete group workflow: list, create profile/post, retrieve."""
        # Given: Initial state
        feed_url = "https://example.com/social.org"

        # Step 1: List groups
        response = self.client.get("/groups/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 3)

        # Step 2: Create profile (simulating what would happen via feed parsing)
        profile = Profile.objects.create(feed=feed_url)

        # Step 3: Create posts in group (simulating what would happen via feed parsing)
        Post.objects.create(
            profile=profile,
            post_id="2025-01-01T12:00:00+00:00",
            content="My emacs config",
            group="emacs",
        )

        # Step 4: Retrieve group messages
        response = self.client.get("/groups/emacs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        # Check that we have a post from the feed we registered
        self.assertIn(
            "https://example.com/social.org#", response.data["data"][0]["post"]
        )

        # Step 5: Verify groups list still works
        response = self.client.get("/groups/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should contain display name, not slug
        self.assertIn("Emacs", response.data["data"])

    @override_settings(ENABLED_GROUPS=[], GROUPS_MAP={})
    def test_groups_disabled(self):
        """Test behavior when groups are not configured."""
        # When: We try to access any group endpoint
        response = self.client.get("/groups/")

        # Then: Should indicate no groups configured
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("No groups configured", response.data["errors"][0])
