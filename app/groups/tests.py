from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post
from app.groups.models import GroupMember


class GroupsViewTest(TestCase):
    """Test cases for the GroupsView API."""

    def setUp(self):
        self.client = APIClient()
        self.groups_url = "/groups/"

    @override_settings(ENABLED_GROUPS=[])
    def test_no_groups_configured(self):
        """Test GET /groups/ when no groups are configured."""
        # Given: No groups configured

        # When: We request groups list
        response = self.client.get(self.groups_url)

        # Then: Should return 404 with error message
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("No groups configured", response.data["errors"][0])

    @override_settings(ENABLED_GROUPS=["emacs", "org-social", "python"])
    def test_list_groups_success(self):
        """Test GET /groups/ returns configured groups."""
        # Given: Groups configured

        # When: We request groups list
        response = self.client.get(self.groups_url)

        # Then: Should return success with group names
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(len(response.data["data"]), 3)
        self.assertEqual(response.data["data"], ["emacs", "org-social", "python"])

    @override_settings(ENABLED_GROUPS=["emacs", "org-social"])
    def test_list_groups_empty_groups(self):
        """Test GET /groups/ when groups are configured."""
        # Given: Groups configured

        # When: We request groups list
        response = self.client.get(self.groups_url)

        # Then: Should return group names
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(len(response.data["data"]), 2)
        self.assertEqual(response.data["data"], ["emacs", "org-social"])


class GroupMembersViewTest(TestCase):
    """Test cases for the GroupMembersView API."""

    def setUp(self):
        self.client = APIClient()

    @override_settings(ENABLED_GROUPS=["emacs", "org-social", "python"])
    def test_register_member_success(self):
        """Test POST /groups/{id}/members/ registers a feed."""
        # Given: A valid group ID and feed URL
        feed_url = "https://example.com/social.org"

        # When: We register the feed as a member
        response = self.client.post(
            "/groups/emacs/members/", QUERY_STRING=f"feed={feed_url}"
        )

        # Then: Should return success
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["data"]["group"], "emacs")
        self.assertEqual(response.data["data"]["feed"], feed_url)

        # Verify membership was created
        self.assertTrue(
            GroupMember.objects.filter(
                group_name="emacs", profile__feed=feed_url
            ).exists()
        )

    @override_settings(ENABLED_GROUPS=["emacs", "org-social"])
    def test_register_member_already_exists(self):
        """Test registering an already registered member."""
        # Given: A feed already registered in a group
        feed_url = "https://example.com/social.org"
        profile = Profile.objects.create(feed=feed_url)
        GroupMember.objects.create(group_name="emacs", profile=profile)

        # When: We try to register again
        response = self.client.post(
            "/groups/emacs/members/", QUERY_STRING=f"feed={feed_url}"
        )

        # Then: Should return success with message
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertIn("Already a member", response.data["data"]["message"])

    @override_settings(ENABLED_GROUPS=["emacs"])
    def test_register_member_invalid_group(self):
        """Test registering with invalid group ID."""
        # Given: An invalid group ID
        feed_url = "https://example.com/social.org"

        # When: We try to register with invalid group name
        response = self.client.post(
            "/groups/invalid-group/members/", QUERY_STRING=f"feed={feed_url}"
        )

        # Then: Should return 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("does not exist", response.data["errors"][0])

    @override_settings(ENABLED_GROUPS=["emacs"])
    def test_register_member_missing_feed(self):
        """Test registering without feed parameter."""
        # Given: No feed parameter

        # When: We try to register without feed
        response = self.client.post("/groups/emacs/members/")

        # Then: Should return 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("feed parameter is required", response.data["errors"][0])

    @override_settings(ENABLED_GROUPS=["emacs", "org-social"])
    def test_register_member_url_encoded(self):
        """Test registering with URL-encoded feed."""
        # Given: A URL-encoded feed
        feed_url = "https://example.com/social.org"
        encoded_url = "https%3A%2F%2Fexample.com%2Fsocial.org"

        # When: We register with encoded URL
        response = self.client.post(
            "/groups/emacs/members/", QUERY_STRING=f"feed={encoded_url}"
        )

        # Then: Should decode and register successfully
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["feed"], feed_url)


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

    @override_settings(ENABLED_GROUPS=["emacs", "python"])
    def test_get_group_messages_success(self):
        """Test GET /groups/{id}/ returns group messages."""
        # Given: Posts with group metadata
        # Join groups first
        GroupMember.objects.create(group_name="emacs", profile=self.profile1)
        GroupMember.objects.create(group_name="emacs", profile=self.profile2)

        Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="First emacs post",
        )
        Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="Second emacs post",
        )
        # Post from non-member (should not appear)
        other_profile = Profile.objects.create(
            feed="https://other.com/social.org", nick="other"
        )
        Post.objects.create(
            profile=other_profile,
            post_id="2025-01-01T14:00:00+00:00",
            content="Other post",
        )

        # When: We request emacs group messages
        response = self.client.get("/groups/emacs/")

        # Then: Should return only emacs posts
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(len(response.data["data"]), 2)

        # Check meta
        self.assertEqual(response.data["meta"]["group"], "emacs")
        self.assertIn("members", response.data["meta"])
        self.assertIn("version", response.data["meta"])

    @override_settings(ENABLED_GROUPS=["emacs"])
    def test_get_group_messages_with_replies(self):
        """Test group messages with reply tree structure."""
        # Given: Posts with replies in group
        GroupMember.objects.create(group_name="emacs", profile=self.profile1)
        GroupMember.objects.create(group_name="emacs", profile=self.profile2)

        post1 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="Original post",
        )
        Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="Reply to post1",
            reply_to=f"{self.profile1.feed}#{post1.post_id}",
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

    @override_settings(ENABLED_GROUPS=["emacs"])
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

    @override_settings(ENABLED_GROUPS=["emacs"])
    def test_get_group_messages_invalid_group(self):
        """Test getting messages from invalid group."""
        # Given: Invalid group ID

        # When: We request invalid group
        response = self.client.get("/groups/invalid-group/")

        # Then: Should return 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")

    @override_settings(ENABLED_GROUPS=["emacs", "python"])
    def test_get_group_messages_caching(self):
        """Test that group messages are cached."""
        # Given: Posts in group
        GroupMember.objects.create(group_name="emacs", profile=self.profile1)

        Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="Test post",
        )

        # When: We request group messages twice
        response1 = self.client.get("/groups/emacs/")
        response2 = self.client.get("/groups/emacs/")

        # Then: Both should succeed
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # And version should be the same (indicating cache hit)
        self.assertEqual(
            response1.data["meta"]["version"], response2.data["meta"]["version"]
        )


class GroupsIntegrationTest(TestCase):
    """Integration tests for groups functionality."""

    def setUp(self):
        self.client = APIClient()

    @override_settings(ENABLED_GROUPS=["emacs", "org-social", "python"])
    def test_full_group_workflow(self):
        """Test complete group workflow: list, join, post, retrieve."""
        # Given: Initial state
        feed_url = "https://example.com/social.org"

        # Step 1: List groups
        response = self.client.get("/groups/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 3)

        # Step 2: Join emacs group
        response = self.client.post(
            "/groups/emacs/members/", QUERY_STRING=f"feed={feed_url}"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Step 3: Create posts in group (simulating what would happen via feed parsing)
        profile = Profile.objects.get(feed=feed_url)
        Post.objects.create(
            profile=profile,
            post_id="2025-01-01T12:00:00+00:00",
            content="My emacs config",
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
        self.assertIn("emacs", response.data["data"])

    @override_settings(ENABLED_GROUPS=[])
    def test_groups_disabled(self):
        """Test behavior when groups are not configured."""
        # When: We try to access any group endpoint
        response = self.client.get("/groups/")

        # Then: Should indicate no groups configured
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("No groups configured", response.data["errors"][0])
