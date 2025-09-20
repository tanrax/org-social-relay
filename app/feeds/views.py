from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging

from .models import Feed, Profile, Mention
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
        import hashlib

        version_string = f"{profile.last_updated.isoformat()}_{len(mentions_data)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        response_data = {
            "type": "Success",
            "errors": [],
            "data": mentions_data,
            "meta": {"feed": feed_url, "total": len(mentions_data), "version": version},
        }

        # Cache for 5 minutes (300 seconds)
        cache.set(cache_key, response_data, 300)

        return Response(response_data, status=status.HTTP_200_OK)
