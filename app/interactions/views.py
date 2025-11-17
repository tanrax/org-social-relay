from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging

from app.feeds.models import Post, Profile
from app.feeds.utils import get_parent_chain
from app.reactions.utils import get_reactions_for_post
from app.replies.utils import get_direct_replies_for_post
from app.boosts.utils import get_boosts_for_post

logger = logging.getLogger(__name__)


class InteractionsView(APIView):
    """Get all interactions (reactions, replies, boosts) for a specific post"""

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

        cache_key = f"interactions_{feed_url}_{post_id}"
        cached_response = cache.get(cache_key)

        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

        # Find the original post
        try:
            profile = Profile.objects.get(feed=feed_url)
            original_post = Post.objects.get(profile=profile, post_id=post_id)
        except (Profile.DoesNotExist, Post.DoesNotExist):
            return Response(
                {
                    "type": "Error",
                    "errors": ["Post not found"],
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        original_post_url = f"{feed_url}#{post_id}"

        # Get reactions using shared utility function
        reactions_qs = get_reactions_for_post(original_post_url)
        reactions_data = [
            {
                "post": f"{reaction.profile.feed}#{reaction.post_id}",
                "emoji": reaction.mood,
            }
            for reaction in reactions_qs
        ]

        # Get replies using shared utility function
        replies_qs = get_direct_replies_for_post(original_post_url)
        replies_data = [f"{reply.profile.feed}#{reply.post_id}" for reply in replies_qs]

        # Get boosts using shared utility function
        boosts_qs = get_boosts_for_post(original_post_url)
        boosts_data = [f"{boost.profile.feed}#{boost.post_id}" for boost in boosts_qs]

        # Get parent chain
        parent_chain = get_parent_chain(original_post)

        # URL encode the post_url for the self link
        from urllib.parse import quote

        encoded_post_url = quote(post_url, safe="")
        encoded_feed_url = quote(feed_url, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": {
                "reactions": reactions_data,
                "replies": replies_data,
                "boosts": boosts_data,
            },
            "meta": {
                "post": original_post_url,
                "total_reactions": len(reactions_data),
                "total_replies": len(replies_data),
                "total_boosts": len(boosts_data),
                "parentChain": parent_chain,
            },
            "_links": {
                "self": {
                    "href": f"/interactions/?post={encoded_post_url}",
                    "method": "GET",
                },
                "reactions": {
                    "href": f"/reactions/?feed={encoded_feed_url}",
                    "method": "GET",
                },
                "replies": {
                    "href": f"/replies/?post={encoded_post_url}",
                    "method": "GET",
                },
                "boosts": {
                    "href": f"/boosts/?post={encoded_post_url}",
                    "method": "GET",
                },
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
