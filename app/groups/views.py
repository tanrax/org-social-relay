import hashlib
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.core.cache import cache

from app.feeds.models import Post, Profile


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

        # Return group names (not slugs)
        groups_data = list(settings.GROUPS_MAP.values())

        # Build individual group links (name + slug in href)
        group_links = []
        for slug, name in settings.GROUPS_MAP.items():
            group_links.append(
                {"name": name, "href": f"/groups/{slug}/", "method": "GET"}
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

    def get(self, request, group_slug):
        """GET /groups/{group_slug}/ - Get messages from a group."""
        # Validate group_slug
        if group_slug not in settings.ENABLED_GROUPS:
            return Response(
                {
                    "type": "Error",
                    "errors": [f"Group '{group_slug}' does not exist"],
                    "data": [],
                    "meta": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get display name from slug
        group_display_name = settings.GROUPS_MAP[group_slug]

        # Try to get from cache
        cache_key = f"group_messages:{group_slug}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        # Get all posts for this group
        group_posts = (
            Post.objects.filter(group=group_slug)
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

        # Get group members (unique profiles that have posted in this group)
        member_profiles = Profile.objects.filter(posts__group=group_slug).distinct()
        members_list = [profile.feed for profile in member_profiles]

        # Generate version hash
        version_string = "".join(sorted([p["post"] for p in messages_tree]))
        version = hashlib.sha256(version_string.encode()).hexdigest()[:8]

        # URL encode the group_slug for the join link template
        from urllib.parse import quote

        encoded_group_slug = quote(group_slug, safe="")

        response_data = {
            "type": "Success",
            "errors": [],
            "data": messages_tree,
            "meta": {
                "group": group_display_name,
                "members": members_list,
                "version": version,
            },
            "_links": {
                "self": {"href": f"/groups/{encoded_group_slug}/", "method": "GET"},
                "group-list": {"href": "/groups/", "method": "GET"},
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, timeout=None)

        return Response(response_data, status=status.HTTP_200_OK)
