from urllib.parse import quote

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.cache import cache

from app.feeds.models import Follow, Profile


class ProfileView(APIView):
    """Get profile information including followers for a given feed URL."""

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

        cache_key = f"profile_{feed_url}"
        cached_response = cache.get(cache_key)
        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

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

        followers = (
            Follow.objects.filter(followed=profile)
            .select_related("follower")
            .order_by("follower__feed")
        )
        follower_feeds = [f.follower.feed for f in followers]

        encoded_feed_url = quote(feed_url, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": {
                "feed": feed_url,
                "followers": follower_feeds,
            },
            "meta": {
                "feed": feed_url,
                "total_followers": len(follower_feeds),
            },
            "_links": {
                "self": {
                    "href": f"/profile/?feed={encoded_feed_url}",
                    "method": "GET",
                }
            },
        }

        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
