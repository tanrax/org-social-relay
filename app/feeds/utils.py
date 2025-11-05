"""
Utility functions for working with posts and feeds
"""

from typing import List
from app.feeds.models import Post, Profile


def get_parent_chain(post: Post, max_depth: int = 100) -> List[str]:
    """
    Calculate the parent chain for a post.

    Returns a list of post URLs from the root ancestor to the immediate parent.
    For example, if the chain is: Alice → Bob → Carol → Dave → Current post
    This returns: [Alice_URL, Bob_URL, Carol_URL, Dave_URL]

    Args:
        post: The Post object to calculate the chain for
        max_depth: Maximum depth to traverse (prevents infinite loops)

    Returns:
        List of post URLs in order from root to immediate parent
    """
    if not post.reply_to:
        # This post is a root post (no parent)
        return []

    chain = []
    current_reply_to = post.reply_to
    depth = 0

    while current_reply_to and depth < max_depth:
        # Add current parent to chain
        chain.append(current_reply_to)

        # Parse the reply_to URL to find the parent post
        try:
            if "#" not in current_reply_to:
                break
            feed_url, post_id = current_reply_to.split("#", 1)

            # Find the parent post
            profile = Profile.objects.filter(feed=feed_url).first()
            if not profile:
                break

            parent_post = Post.objects.filter(profile=profile, post_id=post_id).first()

            if not parent_post:
                break

            # Move up to the next parent
            current_reply_to = parent_post.reply_to
            depth += 1

        except (ValueError, AttributeError):
            break

    # Reverse the chain so it goes from root to immediate parent
    chain.reverse()

    return chain
