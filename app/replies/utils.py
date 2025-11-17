"""
Utility functions for replies
"""

from django.db.models import Q
from app.feeds.models import Post


def get_direct_replies_for_post(post_url: str):
    """
    Get direct replies for a specific post.
    Excludes reactions (posts with mood) and poll votes.

    Args:
        post_url: The post URL in format feed_url#post_id

    Returns:
        QuerySet of Post objects that are direct replies to the given post
    """
    return (
        Post.objects.filter(reply_to=post_url)
        .filter(Q(mood="") | Q(mood__isnull=True))
        .exclude(poll_votes__isnull=False)
        .select_related("profile")
        .order_by("-post_id")
    )
