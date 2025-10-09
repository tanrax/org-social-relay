import hashlib
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.core.cache import cache

from app.feeds.models import Post
from .models import GroupMember


class GroupsView(APIView):
    """List all groups configured in the relay."""

    def get(self, request):
        """GET /groups/ - List all groups from the relay."""
        # Check if groups are configured
        if not settings.ENABLED_GROUPS:
            return Response(
                {
                    "type": "Error",
                    "errors": ["No groups configured in this relay"],
                    "data": [],
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Simple group list - just the group names
        groups_data = list(settings.ENABLED_GROUPS)

        # Build individual group links
        group_links = []
        for group_name in settings.ENABLED_GROUPS:
            group_links.append(
                {"name": group_name, "href": f"/groups/{group_name}/", "method": "GET"}
            )

        return Response(
            {
                "type": "Success",
                "errors": [],
                "data": groups_data,
                "_links": {
                    "self": {"href": "/groups/", "method": "GET"},
                    "groups": group_links,
                },
            },
            status=status.HTTP_200_OK,
        )


class GroupMessagesView(APIView):
    """Get messages from a group."""

    def get(self, request, group_name):
        """GET /groups/{group_name}/ - Get messages from a group."""
        # Validate group_name
        if group_name not in settings.ENABLED_GROUPS:
            return Response(
                {
                    "type": "Error",
                    "errors": [f"Group '{group_name}' does not exist"],
                    "data": [],
                    "meta": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Try to get from cache
        cache_key = f"group_messages:{group_name}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        # Get all posts from members of this group
        # TODO: When group field is added to Post model, filter by group
        group_members = GroupMember.objects.filter(group_name=group_name).values_list(
            "profile_id", flat=True
        )
        group_posts = (
            Post.objects.filter(profile_id__in=group_members)
            .select_related("profile")
            .order_by("-created_at")
        )

        # Build tree structure for messages (similar to replies)
        messages_tree = []
        posts_dict = {}

        # First pass: Create post URLs and dict
        for post in group_posts:
            post_url = f"{post.profile.feed}#{post.post_id}"
            posts_dict[post_url] = {
                "post": post_url,
                "children": [],
                "reply_to": post.reply_to if post.reply_to else None,
            }

        # Second pass: Build tree structure
        for post_url, post_data in posts_dict.items():
            if post_data["reply_to"]:
                # This is a reply, add it to parent's children
                parent_url = post_data["reply_to"]
                if parent_url in posts_dict:
                    posts_dict[parent_url]["children"].append(
                        {
                            "post": post_url,
                            "children": post_data["children"],
                        }
                    )
                else:
                    # Parent not in group, add as top-level
                    messages_tree.append(
                        {
                            "post": post_url,
                            "children": post_data["children"],
                        }
                    )
            else:
                # Top-level post
                messages_tree.append(
                    {
                        "post": post_url,
                        "children": post_data["children"],
                    }
                )

        # Get group members
        group_members = GroupMember.objects.filter(
            group_name=group_name
        ).select_related("profile")
        members_list = [member.profile.feed for member in group_members]

        # Generate version hash
        version_string = "".join(sorted([p["post"] for p in messages_tree]))
        version = hashlib.sha256(version_string.encode()).hexdigest()[:8]

        # URL encode the group_name for the join link template
        from urllib.parse import quote

        encoded_group_name = quote(group_name, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": messages_tree,
            "meta": {
                "group": group_name,
                "members": members_list,
                "version": version,
            },
            "_links": {
                "self": {"href": f"/groups/{encoded_group_name}/", "method": "GET"},
                "group-list": {"href": "/groups/", "method": "GET"},
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, timeout=None)

        return Response(response_data, status=status.HTTP_200_OK)
