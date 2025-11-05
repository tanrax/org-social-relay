from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from django.db.models import Q
import logging
import hashlib

from app.feeds.models import Profile, Post

logger = logging.getLogger(__name__)


class RepliesToView(APIView):
    """Get replies to posts from a specific feed URL"""

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

        # Try to get replies from cache first
        cache_key = f"repliesto_{feed_url}"
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

        # Get all replies to this profile's posts
        # A reply is a post with reply_to != '' but WITHOUT mood (reactions) and WITHOUT poll_option (poll votes)
        # We need to find posts that reply to our profile's posts but are not reactions or votes

        # First, get all post IDs from this profile
        profile_post_ids = list(profile.posts.values_list("post_id", flat=True))

        # Build the reply_to patterns (feed#post_id)
        reply_to_patterns = [f"{feed_url}#{post_id}" for post_id in profile_post_ids]

        # Find all posts that reply to any of this profile's posts
        # Exclude posts with mood (reactions) and posts that are poll votes
        replies = (
            Post.objects.filter(reply_to__in=reply_to_patterns)
            .filter(Q(mood="") | Q(mood__isnull=True))
            .exclude(poll_votes__isnull=False)
            .select_related("profile")
            .order_by("-post_id")
        )

        # Build data according to README spec
        replies_data = []
        for reply in replies:
            reply_data = {
                "post": f"{reply.profile.feed}#{reply.post_id}",
                "parent": reply.reply_to,
            }
            replies_data.append(reply_data)

        # Generate version hash based on profile's last update and replies count
        version_string = f"{profile.last_updated.isoformat()}_{len(replies_data)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        # URL encode the feed_url for the self link
        from urllib.parse import quote

        encoded_feed_url = quote(feed_url, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": replies_data,
            "meta": {"feed": feed_url, "total": len(replies_data), "version": version},
            "_links": {
                "self": {
                    "href": f"/replies-to/?feed={encoded_feed_url}",
                    "method": "GET",
                }
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
