from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging
import hashlib

from app.feeds.models import Profile, Mention

logger = logging.getLogger(__name__)


class MentionsView(APIView):
    """Get mentions for a specific feed URL"""

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

        # Try to get mentions from cache first
        cache_key = f"mentions_{feed_url}"
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

        # Get all mentions for this profile, ordered by post date (most recent first)
        mentions = (
            Mention.objects.filter(mentioned_profile=profile)
            .select_related("post", "post__profile")
            .order_by("-post__post_id")
        )

        # Build data according to README spec - just post URLs
        mentions_data = []
        for mention in mentions:
            post_url = f"{mention.post.profile.feed}#{mention.post.post_id}"
            mentions_data.append(post_url)

        # Generate version hash based on profile's last update and mentions count
        version_string = f"{profile.last_updated.isoformat()}_{len(mentions_data)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        # URL encode the feed_url for the self link
        from urllib.parse import quote

        encoded_feed_url = quote(feed_url, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": mentions_data,
            "meta": {"feed": feed_url, "total": len(mentions_data), "version": version},
            "_links": {
                "self": {"href": f"/mentions/?feed={encoded_feed_url}", "method": "GET"}
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
