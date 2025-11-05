from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post


class RepliesViewTest(TestCase):
    """Test cases for the RepliesView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.replies_url = "/replies/"

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

        # Create original post
        self.original_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="This is the original post",
        )

        # Create direct replies to original post
        self.reply1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="First reply to original",
            reply_to=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        self.reply2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T14:00:00+00:00",
            content="Second reply to original",
            reply_to=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        # Create nested replies (replies to replies)
        self.nested_reply1 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T15:00:00+00:00",
            content="Reply to first reply",
            reply_to=f"{self.profile2.feed}#{self.reply1.post_id}",
        )

        self.nested_reply2 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T16:00:00+00:00",
            content="Another reply to first reply",
            reply_to=f"{self.profile2.feed}#{self.reply1.post_id}",
        )

        # Create deeply nested reply
        self.deep_nested_reply = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T17:00:00+00:00",
            content="Reply to nested reply",
            reply_to=f"{self.profile3.feed}#{self.nested_reply1.post_id}",
        )

    def test_get_replies_success(self):
        """Test GET /replies/?post=<post_url> returns replies tree structure."""
        # Given: A post with replies exists
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request replies for the post
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: We should get replies successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain tree structure data
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)  # 2 direct replies

        # Then: Each reply should have post and children fields
        for reply in data:
            self.assertIn("post", reply)
            self.assertIn("children", reply)
            self.assertIsInstance(reply["children"], list)

        # Then: Meta should contain correct information
        meta = response.data["meta"]
        self.assertEqual(meta["parent"], post_url)
        self.assertIn("version", meta)

    def test_get_replies_nested_structure(self):
        """Test that replies are properly nested in tree structure."""
        # Given: A post with nested replies exists
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request replies for the post
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: We should get properly nested structure
        data = response.data["data"]

        # Find the first reply which has children
        reply_with_children = None
        for reply in data:
            if reply["post"] == f"{self.profile2.feed}#{self.reply1.post_id}":
                reply_with_children = reply
                break

        self.assertIsNotNone(reply_with_children)
        self.assertEqual(len(reply_with_children["children"]), 2)  # 2 nested replies

        # Then: Check that nested reply has its own child
        nested_reply_with_child = None
        for child in reply_with_children["children"]:
            if child["post"] == f"{self.profile3.feed}#{self.nested_reply1.post_id}":
                nested_reply_with_child = child
                break

        self.assertIsNotNone(nested_reply_with_child)
        self.assertEqual(
            len(nested_reply_with_child["children"]), 1
        )  # 1 deep nested reply

    def test_get_replies_nonexistent_post(self):
        """Test GET /replies/ returns 404 for nonexistent post."""
        # Given: A post ID that doesn't exist
        nonexistent_post_url = f"{self.profile1.feed}#2025-01-01T00:00:00+00:00"

        # When: We request replies for nonexistent post
        response = self.client.get(self.replies_url, {"post": nonexistent_post_url})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Post not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_get_replies_nonexistent_profile(self):
        """Test GET /replies/ returns 404 for nonexistent profile."""
        # Given: A profile feed that doesn't exist
        nonexistent_post_url = (
            f"https://nonexistent.com/social.org#{self.original_post.post_id}"
        )

        # When: We request replies for post from nonexistent profile
        response = self.client.get(self.replies_url, {"post": nonexistent_post_url})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Post not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_get_replies_no_replies(self):
        """Test GET /replies/ returns empty array for post with no replies."""
        # Given: A post with no replies
        lonely_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T20:00:00+00:00",
            content="This post has no replies",
        )
        post_url = f"{self.profile1.feed}#{lonely_post.post_id}"

        # When: We request replies for the post
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: We should get empty array
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"], [])

        # Then: Meta should still be present
        meta = response.data["meta"]
        self.assertEqual(meta["parent"], post_url)
        self.assertIn("version", meta)

    def test_replies_response_format_compliance(self):
        """Test replies response format compliance with README specification."""
        # Given: A post with replies exists
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request replies
        response = self.client.get(self.replies_url, {"post": post_url})

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

        # Then: Data should be array of reply trees
        data = response.data["data"]
        for reply_tree in data:
            self.assertIn("post", reply_tree)
            self.assertIn("children", reply_tree)
            self.assertIn("moods", reply_tree)
            self.assertIsInstance(reply_tree["children"], list)
            self.assertIsInstance(reply_tree["moods"], list)

    def test_replies_view_methods_allowed(self):
        """Test that only GET method is allowed on replies endpoint."""
        # Given: A valid replies URL
        params = {"post": f"{self.profile1.feed}#{self.original_post.post_id}"}

        # When: We try different HTTP methods
        post_response = self.client.post(self.replies_url, params)
        put_response = self.client.put(self.replies_url, params)
        delete_response = self.client.delete(self.replies_url, params)
        patch_response = self.client.patch(self.replies_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_replies_missing_parameters(self):
        """Test that missing required parameters return 400 error."""
        # Given: Replies endpoint

        # When: We request without required parameters
        response = self.client.get(self.replies_url)

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("required", response.data["errors"][0])

    def test_replies_invalid_post_format(self):
        """Test that invalid post URL format returns 400 error."""
        # Given: Replies endpoint

        # When: We request with invalid post format (no # separator)
        response = self.client.get(self.replies_url, {"post": "invalid_url_format"})

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Invalid post URL format", response.data["errors"][0])

    def test_replies_with_moods(self):
        """Test replies with mood reactions are properly included."""
        # Given: An original post
        original_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-02T12:00:00+00:00",
            content="Original post for mood testing",
        )

        # And: A regular reply
        regular_reply = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-02T13:00:00+00:00",
            content="This is a regular reply",
            reply_to=f"{self.profile1.feed}#{original_post.post_id}",
        )

        # And: Mood reactions (empty content + mood + reply_to)
        Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-02T13:30:00+00:00",
            content="",  # Empty content for mood reaction
            mood="❤",
            reply_to=f"{self.profile1.feed}#{original_post.post_id}",
        )

        thumbs_up_reaction = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-02T14:00:00+00:00",
            content="   ",  # Whitespace content for mood reaction
            mood="👍",
            reply_to=f"{self.profile2.feed}#{regular_reply.post_id}",
        )

        rocket_reaction = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-02T14:30:00+00:00",
            content="",
            mood="🚀",
            reply_to=f"{self.profile2.feed}#{regular_reply.post_id}",
        )

        # When: We request replies for the original post
        post_url = f"{self.profile1.feed}#{original_post.post_id}"
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: Should return success with moods included
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        # Should have 1 regular reply
        self.assertEqual(len(data), 1)

        reply_tree = data[0]
        self.assertEqual(
            reply_tree["post"], f"{self.profile2.feed}#{regular_reply.post_id}"
        )

        # Regular reply should have moods (👍 and 🚀)
        self.assertIn("moods", reply_tree)
        moods = reply_tree["moods"]
        self.assertEqual(len(moods), 2)

        # Check moods are correctly grouped
        mood_emojis = [mood["emoji"] for mood in moods]
        self.assertIn("👍", mood_emojis)
        self.assertIn("🚀", mood_emojis)

        # Check posts for each mood
        thumbs_mood = next(mood for mood in moods if mood["emoji"] == "👍")
        rocket_mood = next(mood for mood in moods if mood["emoji"] == "🚀")

        self.assertEqual(len(thumbs_mood["posts"]), 1)
        self.assertEqual(len(rocket_mood["posts"]), 1)
        self.assertIn(
            f"{self.profile1.feed}#{thumbs_up_reaction.post_id}", thumbs_mood["posts"]
        )
        self.assertIn(
            f"{self.profile2.feed}#{rocket_reaction.post_id}", rocket_mood["posts"]
        )

    def test_replies_format_with_moods(self):
        """Test that all replies include moods field even when empty."""
        # Given: A separate original post for this test
        original_post_for_moods = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-03T12:00:00+00:00",
            content="Original post for moods format test",
        )

        # And: A simple reply without any mood reactions
        Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-03T13:00:00+00:00",
            content="Simple reply without reactions",
            reply_to=f"{self.profile1.feed}#{original_post_for_moods.post_id}",
        )

        # When: We request replies
        post_url = f"{self.profile1.feed}#{original_post_for_moods.post_id}"
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: All replies should have moods field
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        self.assertEqual(len(data), 1)
        reply_tree = data[0]

        # Should have moods field even if empty
        self.assertIn("moods", reply_tree)
        self.assertIsInstance(reply_tree["moods"], list)
        self.assertEqual(len(reply_tree["moods"]), 0)

    def test_replies_include_parent_chain(self):
        """Test that all replies include parent_chain field."""
        # Given: A post with replies exists
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request replies for the post
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: All replies should have parent_chain field
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        for reply in data:
            self.assertIn("parent_chain", reply)
            self.assertIsInstance(reply["parent_chain"], list)

            # Check nested replies also have parent_chain
            for child in reply["children"]:
                self.assertIn("parent_chain", child)
                self.assertIsInstance(child["parent_chain"], list)

    def test_parent_chain_order_from_root_to_parent(self):
        """Test that parent_chain is ordered from root to immediate parent."""
        # Given: A deep reply chain exists
        # Chain: original_post -> reply1 -> nested_reply1 -> deep_nested_reply
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request replies
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: Find the deeply nested reply
        data = response.data["data"]

        # Navigate to reply1
        reply1_node = None
        for reply in data:
            if reply["post"] == f"{self.profile2.feed}#{self.reply1.post_id}":
                reply1_node = reply
                break

        self.assertIsNotNone(reply1_node)

        # Navigate to nested_reply1
        nested_reply1_node = None
        for child in reply1_node["children"]:
            if child["post"] == f"{self.profile3.feed}#{self.nested_reply1.post_id}":
                nested_reply1_node = child
                break

        self.assertIsNotNone(nested_reply1_node)

        # Navigate to deep_nested_reply
        deep_nested_node = None
        for grandchild in nested_reply1_node["children"]:
            if (
                grandchild["post"]
                == f"{self.profile2.feed}#{self.deep_nested_reply.post_id}"
            ):
                deep_nested_node = grandchild
                break

        self.assertIsNotNone(deep_nested_node)

        # Then: Verify parent_chain is ordered from root to immediate parent
        parent_chain = deep_nested_node["parent_chain"]

        # Should have 3 parents: original -> reply1 -> nested_reply1
        self.assertEqual(len(parent_chain), 3)

        # Check order: root first, then reply1, then nested_reply1
        self.assertEqual(
            parent_chain[0], f"{self.profile1.feed}#{self.original_post.post_id}"
        )  # Root
        self.assertEqual(
            parent_chain[1], f"{self.profile2.feed}#{self.reply1.post_id}"
        )  # First reply
        self.assertEqual(
            parent_chain[2], f"{self.profile3.feed}#{self.nested_reply1.post_id}"
        )  # Nested reply

    def test_parent_chain_direct_reply_to_root(self):
        """Test that direct reply to root has single-element parent_chain."""
        # Given: A post with direct replies
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request replies
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: Direct replies should have parent_chain with only root
        data = response.data["data"]

        reply1_node = None
        for reply in data:
            if reply["post"] == f"{self.profile2.feed}#{self.reply1.post_id}":
                reply1_node = reply
                break

        self.assertIsNotNone(reply1_node)

        # Parent chain should contain only the root post
        self.assertEqual(len(reply1_node["parent_chain"]), 1)
        self.assertEqual(
            reply1_node["parent_chain"][0],
            f"{self.profile1.feed}#{self.original_post.post_id}",
        )

    def test_parent_chain_consistency_across_siblings(self):
        """Test that sibling replies have consistent parent_chain up to their common ancestor."""
        # Given: Two sibling replies to the same parent
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request replies
        response = self.client.get(self.replies_url, {"post": post_url})

        # Then: Both siblings should share the same parent in their chain
        data = response.data["data"]

        reply1_node = None
        for reply in data:
            if reply["post"] == f"{self.profile2.feed}#{self.reply1.post_id}":
                reply1_node = reply
                break

        # Get two siblings (nested_reply1 and nested_reply2)
        nested1_node = None
        nested2_node = None
        for child in reply1_node["children"]:
            if child["post"] == f"{self.profile3.feed}#{self.nested_reply1.post_id}":
                nested1_node = child
            elif child["post"] == f"{self.profile1.feed}#{self.nested_reply2.post_id}":
                nested2_node = child

        self.assertIsNotNone(nested1_node)
        self.assertIsNotNone(nested2_node)

        # Both siblings should have the same parent_chain (same ancestors)
        self.assertEqual(len(nested1_node["parent_chain"]), 2)
        self.assertEqual(len(nested2_node["parent_chain"]), 2)
        self.assertEqual(nested1_node["parent_chain"], nested2_node["parent_chain"])
