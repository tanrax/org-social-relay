from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging

from app.feeds.models import Post, Profile

logger = logging.getLogger(__name__)


class BoostsView(APIView):
    """Get boosts for a specific post"""

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
            feed_url, post_id = post_url.split("#", 1)
        except ValueError:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Invalid post URL format. Expected: feed_url#post_id"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = f"boosts_{feed_url}_{post_id}"
        cached_response = cache.get(cache_key)

        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

        # Find the original post
        try:
            profile = Profile.objects.get(feed=feed_url)
            Post.objects.get(profile=profile, post_id=post_id)
        except (Profile.DoesNotExist, Post.DoesNotExist):
            return Response(
                {
                    "type": "Error",
                    "errors": ["Post not found"],
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get all boosts for this post
        # A boost is a post with include property pointing to this post
        original_post_url = f"{feed_url}#{post_id}"

        boosts = (
            Post.objects.filter(include=original_post_url)
            .select_related("profile")
            .order_by("-post_id")
        )

        # Build data according to README spec (simple list of post URLs)
        boosts_data = [f"{boost.profile.feed}#{boost.post_id}" for boost in boosts]

        # URL encode the post_url for the self link
        from urllib.parse import quote

        encoded_post_url = quote(post_url, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": boosts_data,
            "meta": {
                "post": original_post_url,
                "total": len(boosts_data),
            },
            "_links": {
                "self": {"href": f"/boosts/?post={encoded_post_url}", "method": "GET"}
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
