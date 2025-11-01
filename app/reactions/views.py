from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging
import hashlib

from app.feeds.models import Profile, Post

logger = logging.getLogger(__name__)


class ReactionsView(APIView):
    """Get reactions for a specific feed URL"""

    def get(self, request):
        feed_url = request.query_params.get("feed")

        if not feed_url or not feed_url.strip():
            return Response(
                {
                    "type": "Error",
                    "errors": ["Feed URL parameter is required"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        feed_url = feed_url.strip()

        # Try to get reactions from cache first
        cache_key = f"reactions_{feed_url}"
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

        # Get all reactions to this profile's posts
        # A reaction is a post with mood != '' and reply_to pointing to this profile's posts

        # First, get all post IDs from this profile
        profile_post_ids = list(profile.posts.values_list("post_id", flat=True))

        # Build the reply_to patterns (feed#post_id)
        reply_to_patterns = [f"{feed_url}#{post_id}" for post_id in profile_post_ids]

        # Find all posts that reply to any of this profile's posts and have a mood
        # Exclude poll votes (posts with poll_votes relationship)
        reactions = (
            Post.objects.filter(reply_to__in=reply_to_patterns, mood__isnull=False)
            .exclude(mood="")
            .exclude(poll_votes__isnull=False)
            .select_related("profile")
            .order_by("-post_id")
        )

        # Build data according to README spec
        reactions_data = []
        for reaction in reactions:
            reaction_data = {
                "post": f"{reaction.profile.feed}#{reaction.post_id}",
                "emoji": reaction.mood,
                "parent": reaction.reply_to,
            }
            reactions_data.append(reaction_data)

        # Generate version hash based on profile's last update and reactions count
        version_string = f"{profile.last_updated.isoformat()}_{len(reactions_data)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        # URL encode the feed_url for the self link
        from urllib.parse import quote

        encoded_feed_url = quote(feed_url, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": reactions_data,
            "meta": {
                "feed": feed_url,
                "total": len(reactions_data),
                "version": version,
            },
            "_links": {
                "self": {
                    "href": f"/reactions/?feed={encoded_feed_url}",
                    "method": "GET",
                }
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
