from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache

from .models import Feed


class FeedsView(APIView):
    """List feeds or add new feed"""

    def get(self, request):
        # Try to get feeds from cache first
        cache_key = "feeds_list"
        cached_feeds = cache.get(cache_key)

        if cached_feeds is not None:
            return Response(
                {"type": "Success", "errors": [], "data": cached_feeds},
                status=status.HTTP_200_OK,
            )

        # If not in cache, query database
        feeds = list(Feed.objects.all().values_list("url", flat=True))

        # Cache for 5 minutes (300 seconds)
        cache.set(cache_key, feeds, 300)

        return Response(
            {"type": "Success", "errors": [], "data": feeds},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        feed_url = request.data.get("feed")

        if not feed_url or not feed_url.strip():
            return Response(
                {"type": "Error", "errors": ["Feed URL is required"], "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create or get feed
        feed, created = Feed.objects.get_or_create(url=feed_url.strip())

        # If a new feed was created, invalidate the cache
        if created:
            cache.delete("feeds_list")

        # Return appropriate status code
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK

        return Response(
            {"type": "Success", "errors": [], "data": {"feed": feed_url.strip()}},
            status=response_status,
        )
