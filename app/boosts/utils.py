"""
Utility functions for boosts
"""

from app.feeds.models import Post


def get_boosts_for_post(post_url: str):
    """
    Get all boosts for a specific post.

    Args:
        post_url: The post URL in format feed_url#post_id

    Returns:
        QuerySet of Post objects that boost the given post
    """
    return (
        Post.objects.filter(include=post_url)
        .select_related("profile")
        .order_by("-post_id")
    )
