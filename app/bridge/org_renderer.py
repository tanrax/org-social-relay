"""
Renders a bridged Profile and its Posts as a virtual social.org file.

The output follows the Org Social syntax so that any client can consume
the bridge URL with a plain #+FOLLOW: line.
"""

from .html_to_org import escape_org_lines


def _meta_value(value):
    """Metadata values must stay on a single line."""
    return " ".join(str(value).split())


def render_profile_org(profile, posts):
    """
    Build the virtual social.org content for a bridged profile.

    Args:
        profile: app.feeds.models.Profile instance
        posts: iterable of app.feeds.models.Post, oldest first

    Returns:
        str: the Org Social file content
    """
    lines = []
    lines.append(f"#+TITLE: {_meta_value(profile.title) or profile.nick}")
    lines.append(f"#+NICK: {_meta_value(profile.nick).replace(' ', '_')}")
    if profile.description:
        lines.append(f"#+DESCRIPTION: {_meta_value(profile.description)}")
    if profile.avatar:
        lines.append(f"#+AVATAR: {_meta_value(profile.avatar)}")
    for link in profile.links.all():
        lines.append(f"#+LINK: {_meta_value(link.url)}")

    lines.append("")
    lines.append("* Posts")

    for post in posts:
        lines.append(f"** {post.post_id}")
        lines.append(":PROPERTIES:")
        if post.language:
            lines.append(f":LANG: {_meta_value(post.language)}")
        if post.tags:
            lines.append(f":TAGS: {_meta_value(post.tags)}")
        lines.append(":END:")
        lines.append("")
        content = escape_org_lines(post.content.strip())
        if content:
            lines.append(content)
            lines.append("")

    return "\n".join(lines) + "\n"
