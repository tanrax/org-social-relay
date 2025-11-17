from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post


class InteractionsViewTest(TestCase):
    """Test cases for the InteractionsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.interactions_url = "/interactions/"

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

        # Create reactions
        self.reaction1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-02-05T13:15:00+0100",
            content="",
            mood="❤",
            reply_to=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        self.reaction2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-02-05T14:30:00+0100",
            content="",
            mood="🚀",
            reply_to=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        # Create replies
        self.reply1 = Post.objects.create(
            profile=self.profile4,
            post_id="2025-02-05T12:30:00+0100",
            content="Great post!",
            mood="",
            reply_to=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        self.reply2 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-02-05T15:00:00+0100",
            content="I agree!",
            mood="",
            reply_to=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        # Create boosts
        self.boost1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-02-05T14:00:00+0100",
            content="Guys, you have to see this!",
            include=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        self.boost2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-02-05T15:30:00+0100",
            content="",
            include=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

    def test_get_interactions_success(self):
        """Test GET /interactions/?post=<post_url> returns all interactions."""
        # Given: A post with reactions, replies, and boosts
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request interactions for the post
        response = self.client.get(self.interactions_url, {"post": post_url})

        # Then: We should get all interactions successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain all three types
        data = response.data["data"]
        self.assertIn("reactions", data)
        self.assertIn("replies", data)
        self.assertIn("boosts", data)

        # Verify reactions
        reactions = data["reactions"]
        self.assertEqual(len(reactions), 2)
        self.assertEqual(reactions[0]["emoji"], "🚀")  # Most recent first
        self.assertEqual(reactions[1]["emoji"], "❤")

        # Verify replies
        replies = data["replies"]
        self.assertEqual(len(replies), 2)
        self.assertIn(f"{self.profile2.feed}#{self.reply2.post_id}", replies)
        self.assertIn(f"{self.profile4.feed}#{self.reply1.post_id}", replies)

        # Verify boosts
        boosts = data["boosts"]
        self.assertEqual(len(boosts), 2)
        self.assertIn(f"{self.profile2.feed}#{self.boost1.post_id}", boosts)
        self.assertIn(f"{self.profile3.feed}#{self.boost2.post_id}", boosts)

        # Verify meta
        meta = response.data["meta"]
        self.assertEqual(meta["post"], post_url)
        self.assertEqual(meta["total_reactions"], 2)
        self.assertEqual(meta["total_replies"], 2)
        self.assertEqual(meta["total_boosts"], 2)
        self.assertEqual(meta["parentChain"], [])  # Original post has no parents

        # Verify links
        links = response.data["_links"]
        self.assertIn("self", links)
        self.assertIn("reactions", links)
        self.assertIn("replies", links)
        self.assertIn("boosts", links)

    def test_get_interactions_with_parent_chain(self):
        """Test GET /interactions/ includes parent chain for reply posts."""
        # Given: A post that is a reply (has parents)
        parent_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-02-05T08:00:00+0100",
            content="Parent post",
        )

        child_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-02-05T09:00:00+0100",
            content="Reply to parent",
            reply_to=f"{self.profile2.feed}#{parent_post.post_id}",
        )

        post_url = f"{self.profile1.feed}#{child_post.post_id}"

        # When: We request interactions for the child post
        response = self.client.get(self.interactions_url, {"post": post_url})

        # Then: Should include parent chain
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        meta = response.data["meta"]
        self.assertIn("parentChain", meta)
        self.assertEqual(len(meta["parentChain"]), 1)
        self.assertEqual(
            meta["parentChain"][0], f"{self.profile2.feed}#{parent_post.post_id}"
        )

    def test_get_interactions_no_interactions(self):
        """Test GET /interactions/ when post has no interactions."""
        # Given: A post without any interactions
        lonely_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-02-05T20:00:00+0100",
            content="Lonely post",
        )
        post_url = f"{self.profile1.feed}#{lonely_post.post_id}"

        # When: We request interactions
        response = self.client.get(self.interactions_url, {"post": post_url})

        # Then: Should return empty arrays
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data["reactions"]), 0)
        self.assertEqual(len(data["replies"]), 0)
        self.assertEqual(len(data["boosts"]), 0)

        meta = response.data["meta"]
        self.assertEqual(meta["total_reactions"], 0)
        self.assertEqual(meta["total_replies"], 0)
        self.assertEqual(meta["total_boosts"], 0)

    def test_get_interactions_missing_post_parameter(self):
        """Test GET /interactions/ without post parameter returns error."""
        # Given: No post parameter provided

        # When: We request interactions without post parameter
        response = self.client.get(self.interactions_url)

        # Then: We should get a 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("'post' parameter is required", response.data["errors"])

    def test_get_interactions_invalid_post_url_format(self):
        """Test GET /interactions/?post=<invalid_url> returns error."""
        # Given: An invalid post URL (missing #)
        invalid_url = "https://example.com/social.org"

        # When: We request interactions with invalid URL
        response = self.client.get(self.interactions_url, {"post": invalid_url})

        # Then: We should get a 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Invalid post URL format", response.data["errors"][0])

    def test_get_interactions_post_not_found(self):
        """Test GET /interactions/?post=<nonexistent_post> returns 404."""
        # Given: A non-existent post URL
        post_url = "https://nonexistent.com/social.org#2025-01-01T00:00:00+00:00"

        # When: We request interactions for non-existent post
        response = self.client.get(self.interactions_url, {"post": post_url})

        # Then: We should get a 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Post not found", response.data["errors"])

    def test_interactions_excludes_poll_votes(self):
        """Test that poll votes are excluded from reactions and replies."""
        # Given: A post with a poll vote (should be excluded)
        poll_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-02-05T16:00:00+0100",
            content="Poll post",
        )

        # Create a poll vote (reply with poll_votes relationship)
        vote_post = Post.objects.create(
            profile=self.profile3,
            post_id="2025-02-05T17:00:00+0100",
            content="",
            reply_to=f"{self.profile1.feed}#{self.original_post.post_id}",
        )

        from app.feeds.models import PollVote

        PollVote.objects.create(
            post=vote_post, poll_post=poll_post, poll_option="Option A"
        )

        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request interactions
        response = self.client.get(self.interactions_url, {"post": post_url})

        # Then: Poll vote should not be in replies or reactions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        vote_url = f"{self.profile3.feed}#{vote_post.post_id}"

        data = response.data["data"]
        self.assertNotIn(vote_url, data["replies"])
        for reaction in data["reactions"]:
            self.assertNotEqual(reaction["post"], vote_url)

    def test_interactions_caching(self):
        """Test that interactions responses are cached."""
        # Given: A post with interactions
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request interactions twice
        response1 = self.client.get(self.interactions_url, {"post": post_url})
        response2 = self.client.get(self.interactions_url, {"post": post_url})

        # Then: Both responses should be identical
        self.assertEqual(response1.data, response2.data)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_interactions_ordered_by_recency(self):
        """Test that all interactions are ordered from most recent to oldest."""
        # Given: A post with interactions
        post_url = f"{self.profile1.feed}#{self.original_post.post_id}"

        # When: We request interactions
        response = self.client.get(self.interactions_url, {"post": post_url})

        # Then: Items should be ordered by post_id descending (most recent first)
        data = response.data["data"]

        # Check reactions order
        if len(data["reactions"]) > 1:
            for i in range(len(data["reactions"]) - 1):
                current_id = data["reactions"][i]["post"].split("#")[1]
                next_id = data["reactions"][i + 1]["post"].split("#")[1]
                self.assertGreater(current_id, next_id)

        # Check replies order
        if len(data["replies"]) > 1:
            for i in range(len(data["replies"]) - 1):
                current_id = data["replies"][i].split("#")[1]
                next_id = data["replies"][i + 1].split("#")[1]
                self.assertGreater(current_id, next_id)

        # Check boosts order
        if len(data["boosts"]) > 1:
            for i in range(len(data["boosts"]) - 1):
                current_id = data["boosts"][i].split("#")[1]
                next_id = data["boosts"][i + 1].split("#")[1]
                self.assertGreater(current_id, next_id)
