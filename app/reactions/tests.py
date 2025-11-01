from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post, PollVote


class ReactionsViewTest(TestCase):
    """Test cases for the ReactionsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.reactions_url = "/reactions/"

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

        # Create reactions (posts with mood and reply_to)
        self.reaction1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T14:00:00+00:00",
            content="",
            mood="👍",
            reply_to=f"{self.profile1.feed}#{self.post1.post_id}",
        )
        self.reaction2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T15:00:00+00:00",
            content="",
            mood="❤️",
            reply_to=f"{self.profile1.feed}#{self.post2.post_id}",
        )

    def test_get_reactions_success(self):
        """Test GET /reactions/?feed=<feed_url> returns reactions for profile's posts."""
        # Given: A profile with posts that have reactions
        feed_url = self.profile1.feed

        # When: We request reactions for the profile
        response = self.client.get(self.reactions_url, {"feed": feed_url})

        # Then: We should get reactions successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain reaction data
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)  # 2 reactions

        # Then: Each reaction should have expected structure
        for reaction in data:
            self.assertIn("post", reaction)
            self.assertIn("emoji", reaction)
            self.assertIn("parent", reaction)
            self.assertIsInstance(reaction["post"], str)
            self.assertIsInstance(reaction["emoji"], str)
            self.assertIsInstance(reaction["parent"], str)
            self.assertIn("#", reaction["post"])
            self.assertIn("#", reaction["parent"])

        # Then: Should contain expected reaction data
        reaction_posts = [r["post"] for r in data]
        expected_url1 = f"{self.profile2.feed}#{self.reaction1.post_id}"
        expected_url2 = f"{self.profile3.feed}#{self.reaction2.post_id}"

        self.assertIn(expected_url1, reaction_posts)
        self.assertIn(expected_url2, reaction_posts)

        # Then: Meta should contain correct information
        meta = response.data["meta"]
        self.assertEqual(meta["feed"], feed_url)
        self.assertEqual(meta["total"], 2)
        self.assertIn("version", meta)

    def test_get_reactions_no_reactions(self):
        """Test GET /reactions/ returns empty array for profile with no reactions."""
        # Given: A profile with no reactions to their posts
        feed_url = self.profile2.feed

        # When: We request reactions for the profile
        response = self.client.get(self.reactions_url, {"feed": feed_url})

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

    def test_get_reactions_nonexistent_profile(self):
        """Test GET /reactions/ returns 404 for nonexistent profile."""
        # Given: A feed URL that doesn't exist
        nonexistent_feed = "https://nonexistent.com/social.org"

        # When: We request reactions for nonexistent profile
        response = self.client.get(self.reactions_url, {"feed": nonexistent_feed})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Profile not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_reactions_missing_parameters(self):
        """Test that missing required parameters return 400 error."""
        # Given: Reactions endpoint

        # When: We request without required parameters
        response = self.client.get(self.reactions_url)

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("required", response.data["errors"][0])

    def test_reactions_response_format_compliance(self):
        """Test reactions response format compliance with README specification."""
        # Given: A profile with reactions exists
        feed_url = self.profile1.feed

        # When: We request reactions
        response = self.client.get(self.reactions_url, {"feed": feed_url})

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

    def test_reactions_view_methods_allowed(self):
        """Test that only GET method is allowed on reactions endpoint."""
        # Given: A valid reactions URL
        params = {"feed": self.profile1.feed}

        # When: We try different HTTP methods
        post_response = self.client.post(self.reactions_url, params)
        put_response = self.client.put(self.reactions_url, params)
        delete_response = self.client.delete(self.reactions_url, params)
        patch_response = self.client.patch(self.reactions_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_reactions_excludes_regular_replies(self):
        """Test that regular replies without mood are not included in reactions."""
        # Given: A regular reply without mood
        Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T16:00:00+00:00",
            content="This is a regular reply",
            mood="",
            reply_to=f"{self.profile1.feed}#{self.post1.post_id}",
        )

        # When: We request reactions
        response = self.client.get(self.reactions_url, {"feed": self.profile1.feed})

        # Then: Should only get reactions with mood, not regular replies
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 2)  # Still only 2 reactions

    def test_reactions_excludes_poll_votes(self):
        """Test that poll votes (POLL_OPTION) are not included in reactions."""
        # Given: A poll post
        poll_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T10:00:00+00:00",
            content="What's your favorite food?\n- [ ] Pizza\n- [ ] Tacos\n- [ ] Sushi",
        )

        # Given: A poll vote with PollVote relationship (correct after parser fix)
        vote_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T11:00:00+00:00",
            content="Voting for Pizza",
            mood="",  # Empty mood (correct after parser fix)
            reply_to=f"{self.profile1.feed}#{poll_post.post_id}",
        )
        PollVote.objects.create(
            post=vote_post,
            poll_post=poll_post,
            poll_option="Pizza",
        )

        # When: We request reactions
        response = self.client.get(self.reactions_url, {"feed": self.profile1.feed})

        # Then: Should only get reactions, not poll votes
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 2)  # Still only 2 reactions

        # Then: Vote post should not be in the reactions
        reaction_posts = [r["post"] for r in response.data["data"]]
        vote_url = f"{self.profile2.feed}#{vote_post.post_id}"
        self.assertNotIn(vote_url, reaction_posts)

    def test_reactions_integration_parser_to_endpoint(self):
        """Integration test: Parse org content with empty properties and verify reactions endpoint.

        This is a regression test for the bug where empty properties (like :MOOD:) would
        incorrectly capture the next property's value (like :POLL_OPTION:) due to a regex
        issue in the parser. This test ensures the complete flow works correctly:
        1. Parser correctly handles empty properties
        2. Database stores correct values
        3. Reactions endpoint excludes poll votes
        """
        # Given: Org content with empty MOOD and POLL_OPTION (the exact bug scenario)
        from app.feeds.parser import parse_org_social_content

        org_content = """#+TITLE: Test User
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-02-01T12:00:00+00:00
:END:

Original poll post

- [ ] Option A
- [ ] Option B

**
:PROPERTIES:
:ID: 2025-02-01T13:00:00+00:00
:TAGS:
:CLIENT: org-social.el
:REPLY_TO: https://example.com/social.org#2025-02-01T12:00:00+00:00
:MOOD:
:POLL_OPTION: Option A
:END:

Voting for Option A
"""

        # When: We parse the content and process it
        parsed = parse_org_social_content(org_content)

        # Then: Verify parser extracted properties correctly (no bug)
        vote_post = parsed["posts"][1]
        self.assertEqual(vote_post["properties"]["client"], "org-social.el")
        self.assertEqual(vote_post["properties"]["poll_option"], "Option A")
        self.assertNotIn(
            "mood", vote_post["properties"]
        )  # Should be empty, not captured
        self.assertNotIn(
            "tags", vote_post["properties"]
        )  # Should be empty, not captured

        # When: We save this to database and query reactions
        # Create profile for the voter
        voter_profile = Profile.objects.create(
            feed="https://voter.com/social.org",
            title="Voter",
            nick="voter",
        )

        # Process the parsed data to create posts and poll votes
        from app.feeds.models import PollOption

        # Create poll post
        poll_post = Post.objects.create(
            profile=self.profile1,
            post_id="2025-02-01T12:00:00+00:00",
            content="Original poll post\n\n- [ ] Option A\n- [ ] Option B",
        )
        PollOption.objects.create(post=poll_post, option_text="Option A", order=0)
        PollOption.objects.create(post=poll_post, option_text="Option B", order=1)

        # Create vote post (with empty mood, as parser should set it)
        vote_post_obj = Post.objects.create(
            profile=voter_profile,
            post_id="2025-02-01T13:00:00+00:00",
            content="Voting for Option A",
            client="org-social.el",
            reply_to=f"{self.profile1.feed}#{poll_post.post_id}",
            mood="",  # Should be empty, not ":POLL_OPTION: Option A"
        )

        # Create the poll vote relationship
        PollVote.objects.create(
            post=vote_post_obj, poll_post=poll_post, poll_option="Option A"
        )

        # Then: Verify the vote does NOT appear in reactions endpoint
        response = self.client.get(self.reactions_url, {"feed": self.profile1.feed})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should only have the 2 original reactions from setUp
        reaction_posts = [r["post"] for r in response.data["data"]]
        vote_url = f"{voter_profile.feed}#{vote_post_obj.post_id}"
        self.assertNotIn(vote_url, reaction_posts)

        # Then: Verify none of the reactions have POLL_OPTION in their emoji
        for reaction in response.data["data"]:
            self.assertNotIn("POLL_OPTION", reaction["emoji"])
