from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import logging
import hashlib

from app.feeds.models import Post, Profile

logger = logging.getLogger(__name__)


class RepliesView(APIView):
    """Get replies for a specific post in tree structure"""

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

        cache_key = f"replies_{feed_url}_{post_id}"
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

        # Get all replies to this post and any nested replies
        original_post_url = f"{feed_url}#{post_id}"

        # First get direct replies
        direct_replies = list(Post.objects.filter(reply_to=original_post_url)
                             .select_related("profile")
                             .order_by("created_at"))

        # Then get all nested replies recursively
        all_replies = list(direct_replies)

        # Get replies to replies (iteratively to capture all levels)
        current_level = direct_replies
        while current_level:
            next_level = []
            for reply in current_level:
                reply_url = f"{reply.profile.feed}#{reply.post_id}"
                nested_replies = list(Post.objects.filter(reply_to=reply_url)
                                     .select_related("profile")
                                     .order_by("created_at"))
                all_replies.extend(nested_replies)
                next_level.extend(nested_replies)
            current_level = next_level

        replies = all_replies

        # Build tree structure
        replies_tree = self._build_replies_tree(replies, original_post_url)

        # Generate version hash
        version_string = f"{original_post.updated_at.isoformat()}_{len(replies)}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        response_data = {
            "type": "Success",
            "errors": [],
            "data": replies_tree,
            "meta": {
                "parent": original_post_url,
                "version": version,
            },
        }

        # Cache for 5 minutes
        cache.set(cache_key, response_data, 300)

        return Response(response_data, status=status.HTTP_200_OK)

    def _build_replies_tree(self, all_replies, parent_url):
        """Build a tree structure of replies"""
        # Create a map of all posts by their URL
        posts_map = {}
        for reply in all_replies:
            reply_url = f"{reply.profile.feed}#{reply.post_id}"
            posts_map[reply_url] = reply

        # Find direct replies to the parent
        direct_replies = [
            reply for reply in all_replies
            if reply.reply_to == parent_url
        ]

        result = []
        for reply in direct_replies:
            reply_url = f"{reply.profile.feed}#{reply.post_id}"

            # Recursively find children of this reply
            children = self._find_children(reply_url, all_replies)

            reply_node = {
                "post": reply_url,
                "children": children
            }
            result.append(reply_node)

        return result

    def _find_children(self, parent_url, all_replies):
        """Recursively find children of a specific post"""
        children = []

        for reply in all_replies:
            if reply.reply_to == parent_url:
                reply_url = f"{reply.profile.feed}#{reply.post_id}"

                # Recursively find children of this reply
                grandchildren = self._find_children(reply_url, all_replies)

                child_node = {
                    "post": reply_url,
                    "children": grandchildren
                }
                children.append(child_node)

        return children