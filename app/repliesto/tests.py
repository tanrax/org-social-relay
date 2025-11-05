from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post, PollVote


class RepliesToViewTest(TestCase):
    """Test cases for the RepliesToView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.repliesto_url = "/replies-to/"

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

        # Create regular replies (posts with reply_to but without mood and poll_votes)
        self.reply1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T14:00:00+00:00",
            content="This is a reply to post 1",
            mood="",
            reply_to=f"{self.profile1.feed}#{self.post1.post_id}",
        )
        self.reply2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T15:00:00+00:00",
            content="This is a reply to post 2",
            reply_to=f"{self.profile1.feed}#{self.post2.post_id}",
        )

        # Create a reaction (should NOT be included in replies)
        self.reaction = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T16:00:00+00:00",
            content="",
            mood="👍",
            reply_to=f"{self.profile1.feed}#{self.post1.post_id}",
        )

    def test_get_replies_success(self):
        """Test GET /replies-to/?feed=<feed_url> returns replies for profile's posts."""
        # Given: A profile with posts that have replies
        feed_url = self.profile1.feed

        # When: We request replies for the profile
        response = self.client.get(self.repliesto_url, {"feed": feed_url})

        # Then: We should get replies successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain reply data
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)  # 2 replies (excluding the reaction)

        # Then: Each reply should have expected structure
        for reply in data:
            self.assertIn("post", reply)
            self.assertIn("parent", reply)
            self.assertIsInstance(reply["post"], str)
            self.assertIsInstance(reply["parent"], str)
            self.assertIn("#", reply["post"])
            self.assertIn("#", reply["parent"])

        # Then: Should contain expected reply data
        reply_posts = [r["post"] for r in data]
        expected_url1 = f"{self.profile2.feed}#{self.reply1.post_id}"
        expected_url2 = f"{self.profile3.feed}#{self.reply2.post_id}"

        self.assertIn(expected_url1, reply_posts)
        self.assertIn(expected_url2, reply_posts)

        # Then: Meta should contain correct information
        meta = response.data["meta"]
        self.assertEqual(meta["feed"], feed_url)
        self.assertEqual(meta["total"], 2)
        self.assertIn("version", meta)

    def test_get_replies_no_replies(self):
        """Test GET /replies-to/ returns empty array for profile with no replies."""
        # Given: A profile with no replies to their posts
        feed_url = self.profile2.feed

        # When: We request replies for the profile
        response = self.client.get(self.repliesto_url, {"feed": feed_url})

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

    def test_get_replies_nonexistent_profile(self):
        """Test GET /replies-to/ returns 404 for nonexistent profile."""
        # Given: A feed URL that doesn't exist
        nonexistent_feed = "https://nonexistent.com/social.org"

        # When: We request replies for nonexistent profile
        response = self.client.get(self.repliesto_url, {"feed": nonexistent_feed})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Profile not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_replies_missing_parameters(self):
        """Test that missing required parameters return 400 error."""
        # Given: Replies-to endpoint

        # When: We request without required parameters
        response = self.client.get(self.repliesto_url)

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("required", response.data["errors"][0])

    def test_replies_response_format_compliance(self):
        """Test replies response format compliance with README specification."""
        # Given: A profile with replies exists
        feed_url = self.profile1.feed

        # When: We request replies
        response = self.client.get(self.repliesto_url, {"feed": feed_url})

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

    def test_replies_view_methods_allowed(self):
        """Test that only GET method is allowed on replies-to endpoint."""
        # Given: A valid replies-to URL
        params = {"feed": self.profile1.feed}

        # When: We try different HTTP methods
        post_response = self.client.post(self.repliesto_url, params)
        put_response = self.client.put(self.repliesto_url, params)
        delete_response = self.client.delete(self.repliesto_url, params)
        patch_response = self.client.patch(self.repliesto_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_replies_excludes_reactions(self):
        """Test that reactions (posts with mood) are not included in replies."""
        # Given: Setup already includes a reaction

        # When: We request replies
        response = self.client.get(self.repliesto_url, {"feed": self.profile1.feed})

        # Then: Should only get regular replies, not reactions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data), 2)  # Only 2 regular replies

        # Then: None of the replies should be the reaction
        reply_posts = [r["post"] for r in data]
        reaction_url = f"{self.profile2.feed}#{self.reaction.post_id}"
        self.assertNotIn(reaction_url, reply_posts)

    def test_replies_excludes_poll_votes(self):
        """Test that poll votes are not included in replies."""
        # Given: A poll vote (post that is a vote on a poll)
        poll_vote_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T17:00:00+00:00",
            content="",
            reply_to=f"{self.profile1.feed}#{self.post1.post_id}",
        )
        # Create the PollVote object that makes this post a poll vote
        PollVote.objects.create(
            post=poll_vote_post,
            poll_post=self.post1,
            poll_option="option1",
        )

        # When: We request replies
        response = self.client.get(self.repliesto_url, {"feed": self.profile1.feed})

        # Then: Should not include the poll vote
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data), 2)  # Still only 2 regular replies

        # Then: The poll vote should not be in the results
        reply_posts = [r["post"] for r in data]
        poll_vote_url = f"{self.profile2.feed}#{poll_vote_post.post_id}"
        self.assertNotIn(poll_vote_url, reply_posts)

    def test_replies_include_parent_chain(self):
        """Test that all replies include parent_chain field."""
        # Given: A profile with replies exists
        feed_url = self.profile1.feed

        # When: We request replies for the profile
        response = self.client.get(self.repliesto_url, {"feed": feed_url})

        # Then: All replies should have parent_chain field
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        for reply in data:
            self.assertIn("parent_chain", reply)
            self.assertIsInstance(reply["parent_chain"], list)

    def test_parent_chain_order_from_root_to_parent(self):
        """Test that parent_chain is ordered from root to immediate parent."""
        # Given: Create a chain: root -> reply_a -> reply_b -> reply_to_profile1
        # First create a root post from profile3
        root_post = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-02T10:00:00+00:00",
            content="Root post",
        )

        # Reply A (profile2 replies to root)
        reply_a = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-02T11:00:00+00:00",
            content="Reply A",
            reply_to=f"{self.profile3.feed}#{root_post.post_id}",
        )

        # Reply B (profile3 replies to reply_a)
        Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-02T12:00:00+00:00",
            content="Reply B",
            reply_to=f"{self.profile2.feed}#{reply_a.post_id}",
        )

        # Final reply to profile1's post (not related to reply_b chain)
        final_reply = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-02T13:00:00+00:00",
            content="Final reply to profile1",
            reply_to=f"{self.profile1.feed}#{self.post1.post_id}",
        )

        # When: We request replies to profile1
        response = self.client.get(self.repliesto_url, {"feed": self.profile1.feed})

        # Then: Find the final_reply in results
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        final_reply_data = None
        for reply in data:
            if reply["post"] == f"{self.profile2.feed}#{final_reply.post_id}":
                final_reply_data = reply
                break

        self.assertIsNotNone(final_reply_data)

        # Then: Verify parent_chain is ordered from root to immediate parent
        parent_chain = final_reply_data["parent_chain"]

        # Should have 1 parent: profile1's post1 (the immediate parent)
        self.assertEqual(len(parent_chain), 1)
        self.assertEqual(parent_chain[0], f"{self.profile1.feed}#{self.post1.post_id}")

    def test_parent_chain_for_reply_to_root(self):
        """Test that replies to root posts have parent_chain with only the root."""
        # Given: Create a root post from profile1 (no parent)
        root_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-03T10:00:00+00:00",
            content="I am a root post with no parent",
        )

        # And: A direct reply to that root post
        direct_reply = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-03T11:00:00+00:00",
            content="Direct reply to root",
            reply_to=f"{self.profile1.feed}#{root_post.post_id}",
        )

        # When: We request replies to profile1
        response = self.client.get(self.repliesto_url, {"feed": self.profile1.feed})

        # Then: Find the direct_reply in results
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        direct_reply_data = None
        for reply in data:
            if reply["post"] == f"{self.profile2.feed}#{direct_reply.post_id}":
                direct_reply_data = reply
                break

        self.assertIsNotNone(direct_reply_data)

        # Then: Parent chain should contain only the root (the immediate parent)
        # parent_chain shows all ancestors from root to immediate parent (inclusive)
        self.assertEqual(len(direct_reply_data["parent_chain"]), 1)
        self.assertEqual(
            direct_reply_data["parent_chain"][0],
            f"{self.profile1.feed}#{root_post.post_id}",
        )

    def test_parent_chain_with_nested_replies(self):
        """Test parent_chain with nested reply structure."""
        # Given: Create a chain where profile1's post has a parent
        # Chain: root_by_profile3 -> profile1's post3 -> reply_to_post3
        root_by_profile3 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-04T10:00:00+00:00",
            content="Root by profile3",
        )

        post3_replies_to_root = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-04T11:00:00+00:00",
            content="Profile1's post replying to root",
            reply_to=f"{self.profile3.feed}#{root_by_profile3.post_id}",
        )

        reply_to_post3 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-04T12:00:00+00:00",
            content="Reply to profile1's post3",
            reply_to=f"{self.profile1.feed}#{post3_replies_to_root.post_id}",
        )

        # When: We request replies to profile1
        response = self.client.get(self.repliesto_url, {"feed": self.profile1.feed})

        # Then: Find reply_to_post3 in results
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        reply_data = None
        for reply in data:
            if reply["post"] == f"{self.profile2.feed}#{reply_to_post3.post_id}":
                reply_data = reply
                break

        self.assertIsNotNone(reply_data)

        # Then: Parent chain should show root -> post3
        parent_chain = reply_data["parent_chain"]

        # Should have 2 ancestors: root and post3
        self.assertEqual(len(parent_chain), 2)

        # Verify order: root first, then post3
        self.assertEqual(
            parent_chain[0], f"{self.profile3.feed}#{root_by_profile3.post_id}"
        )  # Root
        self.assertEqual(
            parent_chain[1], f"{self.profile1.feed}#{post3_replies_to_root.post_id}"
        )  # post3
