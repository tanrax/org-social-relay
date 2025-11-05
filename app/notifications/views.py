from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from django.db.models import Q
import logging

from app.feeds.models import Profile, Post, Mention

logger = logging.getLogger(__name__)


class NotificationsView(APIView):
    """Get all notifications (mentions, reactions, and replies) for a specific feed URL"""

    def get(self, request):
        feed_url = request.query_params.get("feed")
        notification_type = request.query_params.get("type", "").strip().lower()

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

        # Validate type parameter if provided
        valid_types = ["mention", "reaction", "reply"]
        if notification_type and notification_type not in valid_types:
            return Response(
                {
                    "type": "Error",
                    "errors": [
                        f"Invalid type parameter. Must be one of: {', '.join(valid_types)}"
                    ],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Try to get notifications from cache first
        cache_key = f"notifications_{feed_url}_{notification_type}"
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

        notifications_data = []
        counts = {"mentions": 0, "reactions": 0, "replies": 0}

        # Get all post IDs from this profile (for reactions and replies)
        profile_post_ids = list(profile.posts.values_list("post_id", flat=True))
        reply_to_patterns = [f"{feed_url}#{post_id}" for post_id in profile_post_ids]

        # 1. Get mentions (if not filtering or filtering for mentions)
        if not notification_type or notification_type == "mention":
            mentions = (
                Mention.objects.filter(mentioned_profile=profile)
                .select_related("post", "post__profile")
                .order_by("-post__post_id")
            )
            for mention in mentions:
                notifications_data.append(
                    {
                        "type": "mention",
                        "post": f"{mention.post.profile.feed}#{mention.post.post_id}",
                        "_sort_key": mention.post.post_id,  # For sorting
                    }
                )
            counts["mentions"] = len(mentions)

        # 2. Get reactions (if not filtering or filtering for reactions)
        if not notification_type or notification_type == "reaction":
            reactions = (
                Post.objects.filter(reply_to__in=reply_to_patterns, mood__isnull=False)
                .exclude(mood="")
                .select_related("profile")
                .order_by("-post_id")
            )
            for reaction in reactions:
                notifications_data.append(
                    {
                        "type": "reaction",
                        "post": f"{reaction.profile.feed}#{reaction.post_id}",
                        "emoji": reaction.mood,
                        "parent": reaction.reply_to,
                        "_sort_key": reaction.post_id,
                    }
                )
            counts["reactions"] = len(reactions)

        # 3. Get replies (if not filtering or filtering for replies)
        if not notification_type or notification_type == "reply":
            replies = (
                Post.objects.filter(reply_to__in=reply_to_patterns)
                .filter(Q(mood="") | Q(mood__isnull=True))
                .exclude(poll_votes__isnull=False)
                .select_related("profile")
                .order_by("-post_id")
            )
            for reply in replies:
                notifications_data.append(
                    {
                        "type": "reply",
                        "post": f"{reply.profile.feed}#{reply.post_id}",
                        "parent": reply.reply_to,
                        "_sort_key": reply.post_id,
                    }
                )
            counts["replies"] = len(replies)

        # Sort all notifications by post_id (most recent first)
        notifications_data.sort(key=lambda x: x["_sort_key"], reverse=True)

        # Remove the _sort_key field from the final output
        for notification in notifications_data:
            del notification["_sort_key"]

        # URL encode the feed_url for links
        from urllib.parse import quote

        encoded_feed_url = quote(feed_url, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": notifications_data,
            "meta": {
                "feed": feed_url,
                "total": len(notifications_data),
                "by_type": counts,
            },
            "_links": {
                "self": {
                    "href": f"/notifications/?feed={encoded_feed_url}",
                    "method": "GET",
                },
                "mentions": {
                    "href": f"/mentions/?feed={encoded_feed_url}",
                    "method": "GET",
                },
                "reactions": {
                    "href": f"/reactions/?feed={encoded_feed_url}",
                    "method": "GET",
                },
                "replies-to": {
                    "href": f"/replies-to/?feed={encoded_feed_url}",
                    "method": "GET",
                },
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
