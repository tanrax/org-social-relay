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
        PollOption.objects.create(
            post=self.active_poll, option_text="JavaScript", order=2
        )
        PollOption.objects.create(post=self.active_poll, option_text="PHP", order=3)
        PollOption.objects.create(
            post=self.active_poll, option_text="Emacs Lisp", order=4
        )

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
        """Test GET /polls returns all polls URLs (active and expired)."""
        # Given: Active and expired polls exist
        # (Setup already creates these)

        # When: We request all polls
        response = self.client.get(self.polls_url)

        # Then: We should get both active and expired polls as URLs
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 2)  # Both active and expired polls

        # Then: Response should contain poll URLs in the correct format
        expected_active_url = f"{self.profile1.feed}#{self.active_poll.post_id}"
        expected_expired_url = f"{self.profile1.feed}#{self.expired_poll.post_id}"

        self.assertIn(expected_active_url, response.data["data"])
        self.assertIn(expected_expired_url, response.data["data"])

        # Then: All data items should be strings (URLs)
        for poll_url in response.data["data"]:
            self.assertIsInstance(poll_url, str)
            self.assertIn("#", poll_url)  # Should contain the # separator

        # Then: Meta should contain total
        self.assertIn("meta", response.data)
        self.assertEqual(response.data["meta"]["total"], 2)

        # Then: Should have ETag and Last-Modified headers
        self.assertIn("ETag", response)
        self.assertIn("Last-Modified", response)

    def test_get_polls_for_specific_feed(self):
        """Test GET /polls?feed=<url> returns polls for specific feed."""
        # Given: Polls from different profiles exist
        # (Setup already creates these)

        # When: We request polls for a specific feed
        response = self.client.get(self.polls_url, {"feed": self.profile1.feed})

        # Then: We should get polls from that feed only
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 2)  # Both active and expired

        # Then: Response should contain feed metadata
        self.assertEqual(response.data["meta"]["feed"], self.profile1.feed)
        self.assertEqual(response.data["meta"]["total"], 2)

        # Then: Should have ETag and Last-Modified headers
        self.assertIn("ETag", response)
        self.assertIn("Last-Modified", response)

    def test_get_polls_for_nonexistent_feed(self):
        """Test GET /polls?feed=<nonexistent> returns 404."""
        # Given: A feed URL that doesn't exist
        nonexistent_feed = "https://nonexistent.com/social.org"

        # When: We request polls for nonexistent feed
        response = self.client.get(self.polls_url, {"feed": nonexistent_feed})

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
        response = self.client.get(self.polls_url, {"voter": self.profile2.feed})

        # Then: We should get votes cast by that voter
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(len(response.data["data"]), 1)

        # Then: Vote data should be complete
        vote_data = response.data["data"][0]
        self.assertEqual(
            vote_data["vote_post_id"], f"{self.profile2.feed}#{self.vote_post.post_id}"
        )
        self.assertEqual(
            vote_data["poll_id"], f"{self.profile1.feed}#{self.active_poll.post_id}"
        )
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
        response = self.client.get(self.polls_url, {"voter": nonexistent_voter})

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
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
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
        """Test GET /polls/votes/?post=<post_url> returns poll votes."""
        # Given: A poll with votes exists
        poll_votes_url = "/polls/votes/"
        post_url = f"{self.profile1.feed}#{self.poll.post_id}"

        # When: We request votes for the poll
        response = self.client.get(poll_votes_url, {"post": post_url})

        # Then: We should get poll votes successfully
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Response should contain vote data in README format
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)  # 3 options

        # Then: Each option should have the correct structure
        option_names = [item["option"] for item in data]
        self.assertIn("Django", option_names)
        self.assertIn("Flask", option_names)
        self.assertIn("FastAPI", option_names)

        # Then: Check vote counts
        django_votes = next(item for item in data if item["option"] == "Django")[
            "votes"
        ]
        flask_votes = next(item for item in data if item["option"] == "Flask")["votes"]
        fastapi_votes = next(item for item in data if item["option"] == "FastAPI")[
            "votes"
        ]

        self.assertEqual(len(django_votes), 1)
        self.assertEqual(len(flask_votes), 1)
        self.assertEqual(len(fastapi_votes), 0)

        # Then: Votes should be URLs in correct format
        self.assertIn(f"{self.profile2.feed}#{self.vote_post1.post_id}", django_votes)
        self.assertIn(f"{self.profile3.feed}#{self.vote_post2.post_id}", flask_votes)

        # Then: Meta should contain correct information
        meta = response.data["meta"]
        self.assertEqual(meta["poll"], post_url)
        self.assertEqual(meta["total_votes"], 2)

        # Then: Should have ETag and Last-Modified headers
        self.assertIn("ETag", response)
        self.assertIn("Last-Modified", response)

    def test_get_poll_votes_nonexistent_poll(self):
        """Test GET /polls/votes/ returns 404 for nonexistent poll."""
        # Given: A poll ID that doesn't exist
        nonexistent_post_url = f"{self.profile1.feed}#2025-01-01T00:00:00+00:00"
        poll_votes_url = "/polls/votes/"

        # When: We request votes for nonexistent poll
        response = self.client.get(poll_votes_url, {"post": nonexistent_post_url})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()["type"], "Error")
        self.assertIn("Poll not found", response.json()["errors"][0])
        self.assertIsNone(response.json()["data"])

    def test_get_poll_votes_nonexistent_profile(self):
        """Test GET /polls/votes/ returns 404 for nonexistent profile."""
        # Given: A profile feed that doesn't exist
        nonexistent_post_url = f"https://nonexistent.com/social.org#{self.poll.post_id}"
        poll_votes_url = "/polls/votes/"

        # When: We request votes for poll from nonexistent profile
        response = self.client.get(poll_votes_url, {"post": nonexistent_post_url})

        # Then: We should get 404 error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()["type"], "Error")
        self.assertIn("Poll not found", response.json()["errors"][0])
        self.assertIsNone(response.json()["data"])

    def test_get_votes_for_non_poll_post(self):
        """Test GET /polls/votes/ returns 400 for non-poll post."""
        # Given: A regular post (not a poll)
        poll_votes_url = "/polls/votes/"
        non_poll_url = f"{self.profile1.feed}#{self.non_poll.post_id}"

        # When: We request votes for non-poll post
        response = self.client.get(poll_votes_url, {"post": non_poll_url})

        # Then: We should get 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Post is not a poll", response.data["errors"][0])
        self.assertIsNone(response.data["data"])

    def test_poll_votes_response_format_compliance(self):
        """Test poll votes response format compliance."""
        # Given: A poll with votes exists
        poll_votes_url = "/polls/votes/"
        post_url = f"{self.profile1.feed}#{self.poll.post_id}"

        # When: We request poll votes
        response = self.client.get(poll_votes_url, {"post": post_url})

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

        # Then: Data should be array of options with votes
        data = response.data["data"]
        for option in data:
            self.assertIn("option", option)
            self.assertIn("votes", option)
            self.assertIsInstance(option["votes"], list)

    def test_poll_votes_view_methods_allowed(self):
        """Test that only GET method is allowed on poll votes endpoint."""
        # Given: A valid poll votes URL
        poll_votes_url = "/polls/votes/"
        params = {"post": f"{self.profile1.feed}#{self.poll.post_id}"}

        # When: We try different HTTP methods
        post_response = self.client.post(poll_votes_url, params)
        put_response = self.client.put(poll_votes_url, params)
        delete_response = self.client.delete(poll_votes_url, params)
        patch_response = self.client.patch(poll_votes_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_poll_votes_url_encoding_handling(self):
        """Test that special characters in post parameter are handled correctly."""
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

        # When: We request votes using post parameter
        poll_votes_url = "/polls/votes/"
        post_url = f"{special_profile.feed}#{special_poll.post_id}"
        response = self.client.get(poll_votes_url, {"post": post_url})

        # Then: Request should be handled correctly
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        meta = response.data["meta"]
        self.assertEqual(meta["poll"], post_url)

    def test_poll_votes_missing_parameters(self):
        """Test that missing required parameters return 400 error."""
        # Given: Poll votes endpoint
        poll_votes_url = "/polls/votes/"

        # When: We request without required parameters
        response_no_params = self.client.get(poll_votes_url)

        # Then: Should return 400 error
        self.assertEqual(response_no_params.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response_no_params.data["type"], "Error")
        self.assertIn("required", response_no_params.data["errors"][0])

    def test_poll_votes_invalid_post_format(self):
        """Test that invalid post URL format returns 400 error."""
        # Given: Poll votes endpoint
        poll_votes_url = "/polls/votes/"

        # When: We request with invalid post format (no # separator)
        response = self.client.get(poll_votes_url, {"post": "invalid_url_format"})

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Invalid post URL format", response.data["errors"][0])
