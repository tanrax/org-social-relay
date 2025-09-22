from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from django.utils import timezone
import logging
import hashlib

from app.feeds.models import Post, Profile, PollVote

logger = logging.getLogger(__name__)


class PollsView(APIView):
    """List polls or get polls for a specific feed"""

    def get(self, request):
        feed_url = request.query_params.get("feed")
        voter_url = request.query_params.get("voter")

        if voter_url:
            return self._get_voter_polls(voter_url)
        elif feed_url:
            return self._get_feed_polls(feed_url)
        else:
            return self._get_all_polls()

    def _get_all_polls(self):
        """Get all polls in the system (active and expired)"""
        cache_key = "all_polls"
        cached_polls = cache.get(cache_key)

        if cached_polls is not None:
            return Response(
                {"type": "Success", "errors": [], "data": cached_polls},
                status=status.HTTP_200_OK,
            )

        # Get all polls (both active and expired)
        current_time = timezone.now()
        polls = (
            Post.objects.filter(poll_end__isnull=False)
            .select_related("profile")
            .prefetch_related("poll_options")
            .order_by("-created_at")
        )

        polls_data = []
        for poll in polls:
            # According to README, should return simple URL format
            poll_url = f"{poll.profile.feed}#{poll.post_id}"
            polls_data.append(poll_url)

        # Generate version hash for polls
        version_string = f"all_polls_{len(polls_data)}_{current_time.isoformat()}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        response_data = {
            "type": "Success",
            "errors": [],
            "data": polls_data,
            "meta": {
                "total": len(polls_data),
                "version": version,
            },
        }

        # Cache for 5 minutes
        cache.set(cache_key, response_data["data"], 300)

        return Response(response_data, status=status.HTTP_200_OK)

    def _get_feed_polls(self, feed_url):
        """Get polls for a specific feed"""
        feed_url = feed_url.strip()
        cache_key = f"feed_polls_{feed_url}"
        cached_response = cache.get(cache_key)

        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

        # Check if the profile exists
        try:
            profile = Profile.objects.get(feed=feed_url)
        except Profile.DoesNotExist:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Profile not found for the given feed URL"],
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get all polls from this profile
        polls = (
            Post.objects.filter(profile=profile, poll_end__isnull=False)
            .prefetch_related("poll_options")
            .order_by("-created_at")
        )

        polls_data = []
        for poll in polls:
            # Check if poll is still active
            is_active = timezone.now() < poll.poll_end if poll.poll_end else False

            poll_data = {
                "id": f"{poll.profile.feed}#{poll.post_id}",
                "post_id": poll.post_id,
                "content": poll.content,
                "poll_end": poll.poll_end.isoformat(),
                "is_active": is_active,
                "options": [opt.option_text for opt in poll.poll_options.all()],
                "created_at": poll.created_at.isoformat(),
            }
            polls_data.append(poll_data)

        # Generate version hash
        version_string = f"{profile.last_updated.isoformat()}_{len(polls_data)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        response_data = {
            "type": "Success",
            "errors": [],
            "data": polls_data,
            "meta": {
                "feed": feed_url,
                "total": len(polls_data),
                "version": version,
            },
        }

        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)

        return Response(response_data, status=status.HTTP_200_OK)

    def _get_voter_polls(self, voter_url):
        """Get votes cast by a specific voter"""
        voter_url = voter_url.strip()
        cache_key = f"voter_polls_{voter_url}"
        cached_response = cache.get(cache_key)

        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

        # Check if the voter profile exists
        try:
            voter_profile = Profile.objects.get(feed=voter_url)
        except Profile.DoesNotExist:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Voter profile not found for the given feed URL"],
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get all votes cast by this voter
        votes = (
            PollVote.objects.filter(post__profile=voter_profile)
            .select_related("post", "poll_post", "poll_post__profile")
            .order_by("-created_at")
        )

        votes_data = []
        for vote in votes:
            vote_data = {
                "vote_post_id": f"{vote.post.profile.feed}#{vote.post.post_id}",
                "poll_id": f"{vote.poll_post.profile.feed}#{vote.poll_post.post_id}",
                "poll_author": vote.poll_post.profile.nick,
                "poll_content": vote.poll_post.content,
                "selected_option": vote.poll_option,
                "voted_at": vote.created_at.isoformat(),
            }
            votes_data.append(vote_data)

        # Generate version hash
        version_string = f"{voter_profile.last_updated.isoformat()}_{len(votes_data)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        response_data = {
            "type": "Success",
            "errors": [],
            "data": votes_data,
            "meta": {
                "voter": voter_url,
                "total": len(votes_data),
                "version": version,
            },
        }

        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)

        return Response(response_data, status=status.HTTP_200_OK)


class PollVotesView(APIView):
    """Get votes for a specific poll"""

    def get(self, request):
        post_url = request.query_params.get("post")

        if not post_url:
            return Response(
                {
                    "type": "Error",
                    "errors": ["'post' parameter is required"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse the post URL format: https://feed.com/social.org#post_id
        try:
            if "#" not in post_url:
                raise ValueError("Invalid post URL format")
            poll_feed, poll_id = post_url.split("#", 1)
        except ValueError:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Invalid post URL format. Expected: feed_url#post_id"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"poll_votes_{poll_feed}_{poll_id}"
        cached_response = cache.get(cache_key)

        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

        # Find the poll post
        try:
            poll_profile = Profile.objects.get(feed=poll_feed)
            poll_post = Post.objects.get(profile=poll_profile, post_id=poll_id)
        except (Profile.DoesNotExist, Post.DoesNotExist):
            return Response(
                {
                    "type": "Error",
                    "errors": ["Poll not found"],
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verify it's actually a poll
        if not poll_post.is_poll:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Post is not a poll"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get all votes for this poll
        votes = (
            PollVote.objects.filter(poll_post=poll_post)
            .select_related("post", "post__profile")
            .order_by("-created_at")
        )

        # Group votes by option according to README format
        vote_options = {}

        for vote in votes:
            option = vote.poll_option
            vote_post_url = f"{vote.post.profile.feed}#{vote.post.post_id}"

            if option not in vote_options:
                vote_options[option] = []
            vote_options[option].append(vote_post_url)

        # Get poll options for complete results
        poll_options = [opt.option_text for opt in poll_post.poll_options.all()]

        # Build data array according to README format
        data = []
        total_votes = 0
        for option in poll_options:
            option_votes = vote_options.get(option, [])
            total_votes += len(option_votes)
            data.append({"option": option, "votes": option_votes})

        # Generate version hash
        version_string = f"{poll_post.updated_at.isoformat()}_{total_votes}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        response_data = {
            "type": "Success",
            "errors": [],
            "data": data,
            "meta": {
                "poll": f"{poll_feed}#{poll_id}",
                "total_votes": total_votes,
                "version": version,
            },
        }

        # Cache for 2 minutes (shorter cache for vote results)
        cache.set(cache_key, response_data, 120)

        return Response(response_data, status=status.HTTP_200_OK)
