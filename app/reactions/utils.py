"""
Utility functions for reactions
"""

from app.feeds.models import Post


def get_reactions_for_post(post_url: str):
    """
    Get all reactions for a specific post.

    Args:
        post_url: The post URL in format feed_url#post_id

    Returns:
        QuerySet of Post objects that are reactions to the given post
    """
    return (
        Post.objects.filter(reply_to=post_url, mood__isnull=False)
        .exclude(mood="")
        .exclude(poll_votes__isnull=False)
        .select_related("profile")
        .order_by("-post_id")
    )
