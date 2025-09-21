from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from app.feeds.models import Profile, Post, PollOption, PollVote


class PollsViewTest(TestCase):
    """Test cases for the PollsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.polls_url = "/polls/"

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

        # Create a test poll (active)
        self.active_poll = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="What's your favorite programming language?\n\n- [ ] Python\n- [ ] JavaScript\n- [ ] PHP\n- [ ] Emacs Lisp",
            poll_end=timezone.now() + timedelta(hours=1),
        )

        # Create poll options
        PollOption.objects.create(post=self.active_poll, option_text="Python", order=1)
        PollOption.objects.create(post=self.active_poll, option_text="JavaScript", order=2)
        PollOption.objects.create(post=self.active_poll, option_text="PHP", order=3)
        PollOption.objects.create(post=self.active_poll, option_text="Emacs Lisp", order=4)

        # Create an expired poll
        self.expired_poll = Post.objects.create(
            profile=self.profile1,
            post_id="2024-12-01T12:00:00+00:00",
            content="Old poll - What do you think?\n\n- [ ] Yes\n- [ ] No",
            poll_end=timezone.now() - timedelta(hours=1),
        )

        PollOption.objects.create(post=self.expired_poll, option_text="Yes", order=1)
        PollOption.objects.create(post=self.expired_poll, option_text="No", order=2)

        # Create a vote post
        self.vote_post = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="I choose Python!",
            reply_to=f"{self.profile1.feed}#{self.active_poll.post_id}",
        )

        # Create a poll vote
        PollVote.objects.create(
            post=self.vote_post,
            poll_post=self.active_poll,
            poll_option="Python",
        )

    def test_get_all_polls(self):
        """Test GET /polls returns all polls (active and expired)."""
        # Given: Active and expired polls exist
        # (Setup already creates these)

        # When: We request all polls
        response = self.client.get(self.polls_url)

        # Then: We should get both active and expired polls
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 2)  # Both active and expired polls

        # Then: Response should contain poll details with is_active field
        for poll_data in response.data["data"]:
            self.assertIn("id", poll_data)
            self.assertIn("feed", poll_data)
            self.assertIn("author", poll_data)
            self.assertIn("post_id", poll_data)
            self.assertIn("options", poll_data)
            self.assertIn("is_active", poll_data)  # New field to indicate if poll is active
            self.assertIsInstance(poll_data["is_active"], bool)

        # Then: Active poll should be marked as active
        active_poll_data = next(p for p in response.data["data"] if p["post_id"] == self.active_poll.post_id)
        self.assertTrue(active_poll_data["is_active"])

        # Then: Expired poll should be marked as inactive
        expired_poll_data = next(p for p in response.data["data"] if p["post_id"] == self.expired_poll.post_id)
        self.assertFalse(expired_poll_data["is_active"])

    def test_get_polls_for_specific_feed(self):
        """Test GET /polls?feed=<url> returns polls for specific feed."""
        # Given: Polls from different profiles exist
        # (Setup already creates these)

        # When: We request polls for a specific feed
        response = self.client.get(
            self.polls_url, {"feed": self.profile1.feed}
        )

        # Then: We should get polls from that feed only
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 2)  # Both active and expired

        # Then: Response should contain feed metadata
        self.assertEqual(response.data["meta"]["feed"], self.profile1.feed)
        self.assertEqual(response.data["meta"]["total"], 2)
        self.assertIn("version", response.data["meta"])

    def test_get_polls_for_nonexistent_feed(self):
        """Test GET /polls?feed=<nonexistent> returns 404."""
        # Given: A feed URL that doesn't exist
        nonexistent_feed = "https://nonexistent.com/social.org"

        # When: We request polls for nonexistent feed
        response = self.client.get(
            self.polls_url, {"feed": nonexistent_feed}
        )

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Profile not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_get_voter_polls(self):
        """Test GET /polls?voter=<url> returns votes cast by specific voter."""
        # Given: Voter has cast votes
        # (Setup already creates a vote)

        # When: We request votes for a specific voter
        response = self.client.get(
            self.polls_url, {"voter": self.profile2.feed}
        )

        # Then: We should get votes cast by that voter
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 1)

        # Then: Vote data should be complete
        vote_data = response.data["data"][0]
        self.assertEqual(vote_data["vote_post_id"], f"{self.profile2.feed}#{self.vote_post.post_id}")
        self.assertEqual(vote_data["poll_id"], f"{self.profile1.feed}#{self.active_poll.post_id}")
        self.assertEqual(vote_data["poll_author"], self.profile1.nick)
        self.assertEqual(vote_data["selected_option"], "Python")

        # Then: Response should contain voter metadata
        self.assertEqual(response.data["meta"]["voter"], self.profile2.feed)
        self.assertEqual(response.data["meta"]["total"], 1)

    def test_get_voter_polls_nonexistent_voter(self):
        """Test GET /polls?voter=<nonexistent> returns 404."""
        # Given: A voter feed URL that doesn't exist
        nonexistent_voter = "https://nonexistent.com/social.org"

        # When: We request votes for nonexistent voter
        response = self.client.get(
            self.polls_url, {"voter": nonexistent_voter}
        )

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Voter profile not found", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_polls_response_format_compliance(self):
        """Test GET /polls response format compliance."""
        # Given: Polls exist in the database
        # (Setup already creates these)

        # When: We request polls
        response = self.client.get(self.polls_url)

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

    def test_polls_view_methods_allowed(self):
        """Test that only GET method is allowed on polls endpoint."""
        # Given: The polls endpoint

        # When: We try different HTTP methods
        post_response = self.client.post(self.polls_url)
        put_response = self.client.put(self.polls_url)
        delete_response = self.client.delete(self.polls_url)
        patch_response = self.client.patch(self.polls_url)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class PollVotesViewTest(TestCase):
    """Test cases for the PollVotesView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()

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
            feed="https://voter.com/social.org",
            title="Voter Profile",
            nick="voter_user",
            description="Test profile 3",
        )

        # Create a test poll
        self.poll = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="What's your favorite framework?\n\n- [ ] Django\n- [ ] Flask\n- [ ] FastAPI",
            poll_end=timezone.now() + timedelta(hours=1),
        )

        # Create poll options
        PollOption.objects.create(post=self.poll, option_text="Django", order=1)
        PollOption.objects.create(post=self.poll, option_text="Flask", order=2)
        PollOption.objects.create(post=self.poll, option_text="FastAPI", order=3)

        # Create vote posts and poll votes
        self.vote_post1 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="Django is great!",
            reply_to=f"{self.profile1.feed}#{self.poll.post_id}",
        )

        self.vote_post2 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T14:00:00+00:00",
            content="I prefer Flask",
            reply_to=f"{self.profile1.feed}#{self.poll.post_id}",
        )

        PollVote.objects.create(
            post=self.vote_post1,
            poll_post=self.poll,
            poll_option="Django",
        )

        PollVote.objects.create(
            post=self.vote_post2,
            poll_post=self.poll,
            poll_option="Flask",
        )

        # Create a non-poll post for testing
        self.non_poll = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T11:00:00+00:00",
            content="This is just a regular post",
        )

    def test_get_poll_votes_success(self):
        """Test GET /polls/votes/?feed=<feed>&poll_id=<poll_id> returns poll votes."""
        # Given: A poll with votes exists
        poll_votes_url = "/polls/votes/"

        # When: We request votes for the poll
        response = self.client.get(
            poll_votes_url,
            {"feed": self.profile1.feed, "poll_id": self.poll.post_id}
        )

        # Then: We should get poll votes successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain poll information
        poll_data = response.data["data"]["poll"]
        self.assertEqual(poll_data["id"], f"{self.profile1.feed}#{self.poll.post_id}")
        self.assertEqual(poll_data["feed"], self.profile1.feed)
        self.assertEqual(poll_data["author"], self.profile1.nick)
        self.assertEqual(len(poll_data["options"]), 3)

        # Then: Response should contain votes
        votes_data = response.data["data"]["votes"]
        self.assertEqual(len(votes_data), 2)

        # Then: Response should contain vote counts
        vote_counts = response.data["data"]["vote_counts"]
        self.assertEqual(vote_counts["Django"], 1)
        self.assertEqual(vote_counts["Flask"], 1)
        self.assertEqual(vote_counts["FastAPI"], 0)  # No votes for this option

        # Then: Response should contain total votes
        self.assertEqual(response.data["data"]["total_votes"], 2)

    def test_get_poll_votes_nonexistent_poll(self):
        """Test GET /polls/votes/ returns 404 for nonexistent poll."""
        # Given: A poll ID that doesn't exist
        nonexistent_poll_id = "2025-01-01T00:00:00+00:00"
        poll_votes_url = "/polls/votes/"

        # When: We request votes for nonexistent poll
        response = self.client.get(
            poll_votes_url,
            {"feed": self.profile1.feed, "poll_id": nonexistent_poll_id}
        )

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()["type"], "Error")
        self.assertIn("Poll not found", response.json()["errors"][0])
        self.assertIsNone(response.json()["data"])

    def test_get_poll_votes_nonexistent_profile(self):
        """Test GET /polls/votes/ returns 404 for nonexistent profile."""
        # Given: A profile feed that doesn't exist
        nonexistent_feed = "https://nonexistent.com/social.org"
        poll_votes_url = "/polls/votes/"

        # When: We request votes for poll from nonexistent profile
        response = self.client.get(
            poll_votes_url,
            {"feed": nonexistent_feed, "poll_id": self.poll.post_id}
        )

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()["type"], "Error")
        self.assertIn("Poll not found", response.json()["errors"][0])
        self.assertIsNone(response.json()["data"])

    def test_get_votes_for_non_poll_post(self):
        """Test GET /polls/votes/ returns 400 for non-poll post."""
        # Given: A regular post (not a poll)
        poll_votes_url = "/polls/votes/"

        # When: We request votes for non-poll post
        response = self.client.get(
            poll_votes_url,
            {"feed": self.profile1.feed, "poll_id": self.non_poll.post_id}
        )

        # Then: We should get 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Post is not a poll", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_poll_votes_response_format_compliance(self):
        """Test poll votes response format compliance."""
        # Given: A poll with votes exists
        poll_votes_url = "/polls/votes/"

        # When: We request poll votes
        response = self.client.get(
            poll_votes_url,
            {"feed": self.profile1.feed, "poll_id": self.poll.post_id}
        )

        # Then: Response should match expected format
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertIn("meta", response.data)
        self.assertEqual(response.data["type"], "Success")
        self.assertIsInstance(response.data["errors"], list)
        self.assertIsInstance(response.data["data"], dict)
        self.assertIsInstance(response.data["meta"], dict)

        # Then: Data should contain required fields
        data = response.data["data"]
        self.assertIn("poll", data)
        self.assertIn("votes", data)
        self.assertIn("vote_counts", data)
        self.assertIn("total_votes", data)

    def test_poll_votes_view_methods_allowed(self):
        """Test that only GET method is allowed on poll votes endpoint."""
        # Given: A valid poll votes URL
        poll_votes_url = "/polls/votes/"
        params = {"feed": self.profile1.feed, "poll_id": self.poll.post_id}

        # When: We try different HTTP methods
        post_response = self.client.post(poll_votes_url, params)
        put_response = self.client.put(poll_votes_url, params)
        delete_response = self.client.delete(poll_votes_url, params)
        patch_response = self.client.patch(poll_votes_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_poll_votes_url_encoding_handling(self):
        """Test that special characters in feed parameter are handled correctly."""
        # Given: A feed URL that has special characters
        special_profile = Profile.objects.create(
            feed="https://example.com/user name/social.org",
            title="Special Profile",
            nick="special_user",
            description="Profile with special characters",
        )

        special_poll = Post.objects.create(
            profile=special_profile,
            post_id="2025-01-01T15:00:00+00:00",
            content="Test poll with special feed URL",
            poll_end=timezone.now() + timedelta(hours=1),
        )

        # When: We request votes using query parameters
        poll_votes_url = "/polls/votes/"
        response = self.client.get(
            poll_votes_url,
            {"feed": special_profile.feed, "poll_id": special_poll.post_id}
        )

        # Then: Request should be handled correctly
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        poll_data = response.data["data"]["poll"]
        self.assertEqual(poll_data["feed"], special_profile.feed)

    def test_poll_votes_missing_parameters(self):
        """Test that missing required parameters return 400 error."""
        # Given: Poll votes endpoint
        poll_votes_url = "/polls/votes/"

        # When: We request without required parameters
        response_no_params = self.client.get(poll_votes_url)
        response_no_feed = self.client.get(poll_votes_url, {"poll_id": "some_id"})
        response_no_poll_id = self.client.get(poll_votes_url, {"feed": "some_feed"})

        # Then: All should return 400 error
        self.assertEqual(response_no_params.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response_no_feed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response_no_poll_id.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(response_no_params.data["type"], "Error")
        self.assertIn("required", response_no_params.data["errors"][0])