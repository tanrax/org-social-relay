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
        """Get all active polls in the system"""
        cache_key = "all_polls"
        cached_polls = cache.get(cache_key)

        if cached_polls is not None:
            return Response(
                {"type": "Success", "errors": [], "data": cached_polls},
                status=status.HTTP_200_OK,
            )

        # Get all active polls (not expired)
        current_time = timezone.now()
        polls = (
            Post.objects.filter(poll_end__isnull=False, poll_end__gt=current_time)
            .select_related("profile")
            .prefetch_related("poll_options")
            .order_by("-created_at")
        )

        polls_data = []
        for poll in polls:
            poll_data = {
                "id": f"{poll.profile.feed}#{poll.post_id}",
                "feed": poll.profile.feed,
                "author": poll.profile.nick,
                "post_id": poll.post_id,
                "content": poll.content,
                "poll_end": poll.poll_end.isoformat(),
                "options": [opt.option_text for opt in poll.poll_options.all()],
                "created_at": poll.created_at.isoformat(),
            }
            polls_data.append(poll_data)

        # Cache for 5 minutes
        cache.set(cache_key, polls_data, 300)

        return Response(
            {
                "type": "Success",
                "errors": [],
                "data": polls_data,
                "meta": {"total": len(polls_data)},
            },
            status=status.HTTP_200_OK,
        )

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
        poll_feed = request.query_params.get("feed")
        poll_id = request.query_params.get("poll_id")

        if not poll_feed or not poll_id:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Both 'feed' and 'poll_id' parameters are required"],
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

        # Count votes by option
        vote_counts = {}
        votes_data = []

        for vote in votes:
            vote_data = {
                "voter_feed": vote.post.profile.feed,
                "voter_nick": vote.post.profile.nick,
                "selected_option": vote.poll_option,
                "vote_post_id": f"{vote.post.profile.feed}#{vote.post.post_id}",
                "voted_at": vote.created_at.isoformat(),
            }
            votes_data.append(vote_data)

            # Count votes
            if vote.poll_option in vote_counts:
                vote_counts[vote.poll_option] += 1
            else:
                vote_counts[vote.poll_option] = 1

        # Get poll options for complete results
        poll_options = [opt.option_text for opt in poll_post.poll_options.all()]

        # Ensure all options are in vote_counts (even with 0 votes)
        for option in poll_options:
            if option not in vote_counts:
                vote_counts[option] = 0

        # Check if poll is still active
        is_active = timezone.now() < poll_post.poll_end if poll_post.poll_end else False

        # Generate version hash
        version_string = f"{poll_post.updated_at.isoformat()}_{len(votes_data)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        response_data = {
            "type": "Success",
            "errors": [],
            "data": {
                "poll": {
                    "id": f"{poll_feed}#{poll_id}",
                    "feed": poll_feed,
                    "author": poll_post.profile.nick,
                    "content": poll_post.content,
                    "poll_end": poll_post.poll_end.isoformat(),
                    "is_active": is_active,
                    "options": poll_options,
                },
                "votes": votes_data,
                "vote_counts": vote_counts,
                "total_votes": len(votes_data),
            },
            "meta": {
                "poll_id": f"{poll_feed}#{poll_id}",
                "total_votes": len(votes_data),
                "version": version,
            },
        }

        # Cache for 2 minutes (shorter cache for vote results)
        cache.set(cache_key, response_data, 120)

        return Response(response_data, status=status.HTTP_200_OK)