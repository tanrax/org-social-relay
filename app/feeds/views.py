from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging

from .models import Feed
from .parser import validate_org_social_feed

logger = logging.getLogger(__name__)


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

        feed_url = feed_url.strip()

        # Check if feed already exists
        existing_feed = Feed.objects.filter(url=feed_url).first()
        if existing_feed:
            return Response(
                {"type": "Success", "errors": [], "data": {"feed": feed_url}},
                status=status.HTTP_200_OK,
            )

        # Validate the feed before adding it
        logger.info(f"Validating new feed: {feed_url}")
        is_valid, error_message = validate_org_social_feed(feed_url)

        if not is_valid:
            logger.warning(f"Feed validation failed for {feed_url}: {error_message}")
            return Response(
                {
                    "type": "Error",
                    "errors": [f"Invalid Org Social feed: {error_message}"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create the feed
        try:
            Feed.objects.create(url=feed_url)
            logger.info(f"Successfully added new feed: {feed_url}")

            # Invalidate the cache
            cache.delete("feeds_list")

            return Response(
                {"type": "Success", "errors": [], "data": {"feed": feed_url}},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Failed to create feed {feed_url}: {str(e)}")
            return Response(
                {
                    "type": "Error",
                    "errors": ["Failed to add feed to database"],
                    "data": None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


