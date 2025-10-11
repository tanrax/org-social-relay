from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post, Mention


class NotificationsViewTest(TestCase):
    """Test cases for the NotificationsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.notifications_url = "/notifications/"

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

        # Create posts from profile1
        self.post1 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="Original post 1",
        )
        self.post2 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T13:00:00+00:00",
            content="Original post 2",
        )

        # Create a mention
        self.mention_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T14:00:00+00:00",
            content="This post mentions @example_user",
        )
        Mention.objects.create(
            post=self.mention_post,
            mentioned_profile=self.profile1,
            nickname="example_user",
        )

        # Create a reaction
        self.reaction_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T15:00:00+00:00",
            content="",
            mood="👍",
            reply_to=f"{self.profile1.feed}#{self.post1.post_id}",
        )

        # Create a reply
        self.reply_post = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T16:00:00+00:00",
            content="This is a reply to post 2",
            mood="",
            reply_to=f"{self.profile1.feed}#{self.post2.post_id}",
        )

    def test_get_all_notifications_success(self):
        """Test GET /notifications/?feed=<feed_url> returns all notification types."""
        # Given: A profile with mentions, reactions, and replies
        feed_url = self.profile1.feed

        # When: We request all notifications for the profile
        response = self.client.get(self.notifications_url, {"feed": feed_url})

        # Then: We should get notifications successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain all notification types
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)  # 1 mention + 1 reaction + 1 reply

        # Then: Should have different types
        types = {notif["type"] for notif in data}
        self.assertEqual(types, {"mention", "reaction", "reply"})

        # Then: Meta should include by_type breakdown
        meta = response.data["meta"]
        self.assertEqual(meta["feed"], feed_url)
        self.assertEqual(meta["total"], 3)
        self.assertIn("by_type", meta)
        self.assertEqual(meta["by_type"]["mentions"], 1)
        self.assertEqual(meta["by_type"]["reactions"], 1)
        self.assertEqual(meta["by_type"]["replies"], 1)
        self.assertIn("version", meta)

    def test_get_notifications_filtered_by_mention(self):
        """Test GET /notifications/?feed=<feed_url>&type=mention returns only mentions."""
        # Given: A profile with all notification types
        feed_url = self.profile1.feed

        # When: We request only mentions
        response = self.client.get(
            self.notifications_url, {"feed": feed_url, "type": "mention"}
        )

        # Then: Should only return mentions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "mention")

        # Then: Meta should show filtered results
        meta = response.data["meta"]
        self.assertEqual(meta["total"], 1)

    def test_get_notifications_filtered_by_reaction(self):
        """Test GET /notifications/?feed=<feed_url>&type=reaction returns only reactions."""
        # Given: A profile with all notification types
        feed_url = self.profile1.feed

        # When: We request only reactions
        response = self.client.get(
            self.notifications_url, {"feed": feed_url, "type": "reaction"}
        )

        # Then: Should only return reactions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "reaction")
        self.assertIn("emoji", data[0])
        self.assertIn("parent", data[0])

    def test_get_notifications_filtered_by_reply(self):
        """Test GET /notifications/?feed=<feed_url>&type=reply returns only replies."""
        # Given: A profile with all notification types
        feed_url = self.profile1.feed

        # When: We request only replies
        response = self.client.get(
            self.notifications_url, {"feed": feed_url, "type": "reply"}
        )

        # Then: Should only return replies
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "reply")
        self.assertIn("parent", data[0])

    def test_get_notifications_invalid_type(self):
        """Test GET /notifications/ with invalid type parameter returns 400."""
        # Given: A valid feed URL but invalid type
        feed_url = self.profile1.feed

        # When: We request with invalid type
        response = self.client.get(
            self.notifications_url, {"feed": feed_url, "type": "invalid"}
        )

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Invalid type parameter", response.data["errors"][0])

    def test_get_notifications_no_notifications(self):
        """Test GET /notifications/ returns empty array for profile with no notifications."""
        # Given: A profile with no notifications
        feed_url = self.profile2.feed

        # When: We request notifications for the profile
        response = self.client.get(self.notifications_url, {"feed": feed_url})

        # Then: We should get empty array
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"], [])

        # Then: Meta should show zero counts
        meta = response.data["meta"]
        self.assertEqual(meta["feed"], feed_url)
        self.assertEqual(meta["total"], 0)
        self.assertEqual(meta["by_type"]["mentions"], 0)
        self.assertEqual(meta["by_type"]["reactions"], 0)
        self.assertEqual(meta["by_type"]["replies"], 0)

    def test_get_notifications_nonexistent_profile(self):
        """Test GET /notifications/ returns 404 for nonexistent profile."""
        # Given: A feed URL that doesn't exist
        nonexistent_feed = "https://nonexistent.com/social.org"

        # When: We request notifications for nonexistent profile
        response = self.client.get(self.notifications_url, {"feed": nonexistent_feed})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Profile not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_notifications_missing_parameters(self):
        """Test that missing required parameters return 400 error."""
        # Given: Notifications endpoint

        # When: We request without required parameters
        response = self.client.get(self.notifications_url)

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("required", response.data["errors"][0])

    def test_notifications_response_format_compliance(self):
        """Test notifications response format compliance with README specification."""
        # Given: A profile with notifications exists
        feed_url = self.profile1.feed

        # When: We request notifications
        response = self.client.get(self.notifications_url, {"feed": feed_url})

        # Then: Response should match expected format
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertIn("meta", response.data)
        self.assertIn("_links", response.data)
        self.assertEqual(response.data["type"], "Success")
        self.assertIsInstance(response.data["errors"], list)
        self.assertIsInstance(response.data["data"], list)
        self.assertIsInstance(response.data["meta"], dict)

        # Then: Each notification should have type field
        for notification in response.data["data"]:
            self.assertIn("type", notification)
            self.assertIn("post", notification)

    def test_notifications_view_methods_allowed(self):
        """Test that only GET method is allowed on notifications endpoint."""
        # Given: A valid notifications URL
        params = {"feed": self.profile1.feed}

        # When: We try different HTTP methods
        post_response = self.client.post(self.notifications_url, params)
        put_response = self.client.put(self.notifications_url, params)
        delete_response = self.client.delete(self.notifications_url, params)
        patch_response = self.client.patch(self.notifications_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_notifications_sorted_by_post_id(self):
        """Test that notifications are sorted by post_id in descending order."""
        # Given: Multiple notifications with different post_ids
        # (already set up in setUp with ascending timestamps)

        # When: We request all notifications
        response = self.client.get(self.notifications_url, {"feed": self.profile1.feed})

        # Then: Should be sorted by post_id descending (most recent first)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        # Extract post_ids from the notification posts
        post_ids = []
        for notif in data:
            post_url = notif["post"]
            post_id = post_url.split("#")[1]
            post_ids.append(post_id)

        # Then: post_ids should be in descending order
        self.assertEqual(post_ids, sorted(post_ids, reverse=True))

    def test_notifications_mention_structure(self):
        """Test that mention notifications have correct structure."""
        # Given: A profile with a mention
        feed_url = self.profile1.feed

        # When: We request mention notifications
        response = self.client.get(
            self.notifications_url, {"feed": feed_url, "type": "mention"}
        )

        # Then: Mention should have type and post fields only
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mention = response.data["data"][0]
        self.assertEqual(mention["type"], "mention")
        self.assertIn("post", mention)
        self.assertNotIn("emoji", mention)
        self.assertNotIn("parent", mention)

    def test_notifications_reaction_structure(self):
        """Test that reaction notifications have correct structure."""
        # Given: A profile with a reaction
        feed_url = self.profile1.feed

        # When: We request reaction notifications
        response = self.client.get(
            self.notifications_url, {"feed": feed_url, "type": "reaction"}
        )

        # Then: Reaction should have type, post, emoji, and parent fields
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reaction = response.data["data"][0]
        self.assertEqual(reaction["type"], "reaction")
        self.assertIn("post", reaction)
        self.assertIn("emoji", reaction)
        self.assertIn("parent", reaction)

    def test_notifications_reply_structure(self):
        """Test that reply notifications have correct structure."""
        # Given: A profile with a reply
        feed_url = self.profile1.feed

        # When: We request reply notifications
        response = self.client.get(
            self.notifications_url, {"feed": feed_url, "type": "reply"}
        )

        # Then: Reply should have type, post, and parent fields
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reply = response.data["data"][0]
        self.assertEqual(reply["type"], "reply")
        self.assertIn("post", reply)
        self.assertIn("parent", reply)
        self.assertNotIn("emoji", reply)
