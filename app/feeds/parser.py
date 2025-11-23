import re
import requests
from typing import Dict, Any, Tuple
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def _update_feed_last_successful_fetch(url: str):
    """
    Update the last_successful_fetch field for a feed URL.
    This is called when a feed is successfully fetched with HTTP 200.
    """
    try:
        from .models import Feed

        Feed.objects.filter(url=url).update(last_successful_fetch=timezone.now())
    except Exception:
        # Silently fail if Feed model is not available or update fails
        # This prevents breaking existing code during migrations or in tests
        pass


def _handle_feed_redirect(old_url: str, new_url: str):
    """
    Handle feed URL redirect by updating or merging feeds.

    If a feed redirects to a new URL:
    1. Check if new URL already exists as a feed
    2. If yes: merge data and delete old URL
    3. If no: update old URL to new URL

    Args:
        old_url: Original URL that redirected
        new_url: Final URL after redirect
    """
    try:
        from .models import Feed, Profile, Post, Follow, Mention, PollVote
        from django.db import transaction

        old_feed = Feed.objects.filter(url=old_url).first()
        new_feed = Feed.objects.filter(url=new_url).first()

        if old_feed and new_feed:
            # Both URLs exist - merge them
            logger.info(f"Feed redirect detected: {old_url} -> {new_url}")
            logger.info(f"Both feeds exist. Merging old feed into new feed.")

            with transaction.atomic():
                # Get profiles for both feeds
                old_profile = Profile.objects.filter(feed=old_url).first()
                new_profile = Profile.objects.filter(feed=new_url).first()

                if old_profile and new_profile:
                    # Merge profiles - keep the new one, migrate relationships
                    logger.info(f"Merging profile data: {old_profile.nick} -> {new_profile.nick}")

                    # Migrate Follow relationships where old_profile is followed
                    follows_as_followed = Follow.objects.filter(followed=old_profile)
                    for follow in follows_as_followed:
                        # Check if this relationship already exists with new_profile
                        existing = Follow.objects.filter(
                            follower=follow.follower,
                            followed=new_profile
                        ).first()

                        if not existing:
                            # Update to point to new_profile
                            follow.followed = new_profile
                            try:
                                follow.save()
                                logger.debug(f"Migrated follow relationship: {follow.follower.nick} -> {new_profile.nick}")
                            except Exception as e:
                                logger.warning(f"Could not migrate follow relationship, deleting: {e}")
                                follow.delete()
                        else:
                            # Relationship already exists, delete duplicate
                            follow.delete()
                            logger.debug(f"Deleted duplicate follow relationship")

                    # Migrate Follow relationships where old_profile is follower
                    follows_as_follower = Follow.objects.filter(follower=old_profile)
                    for follow in follows_as_follower:
                        # Check if this relationship already exists with new_profile
                        existing = Follow.objects.filter(
                            follower=new_profile,
                            followed=follow.followed
                        ).first()

                        if not existing:
                            # Update to point to new_profile
                            follow.follower = new_profile
                            try:
                                follow.save()
                                logger.debug(f"Migrated follow relationship: {new_profile.nick} -> {follow.followed.nick}")
                            except Exception as e:
                                logger.warning(f"Could not migrate follow relationship, deleting: {e}")
                                follow.delete()
                        else:
                            # Relationship already exists, delete duplicate
                            follow.delete()
                            logger.debug(f"Deleted duplicate follow relationship")

                    # Update all Mentions pointing to old_profile
                    # Mentions don't have unique constraints, so bulk update is safe
                    Mention.objects.filter(mentioned_profile=old_profile).update(mentioned_profile=new_profile)

                    # Migrate posts from old_profile to new_profile (avoid duplicates)
                    old_posts = Post.objects.filter(profile=old_profile)
                    for old_post in old_posts:
                        # Check if post already exists in new profile
                        existing_post = Post.objects.filter(
                            profile=new_profile,
                            post_id=old_post.post_id
                        ).first()

                        if not existing_post:
                            # Migrate post to new profile
                            old_post.profile = new_profile
                            old_post.save()
                            logger.debug(f"Migrated post {old_post.post_id} to new profile")
                        else:
                            # Post already exists, handle poll votes carefully
                            # Get all poll votes pointing to old_post
                            poll_votes = PollVote.objects.filter(poll_post=old_post)
                            for poll_vote in poll_votes:
                                try:
                                    # Check if this vote already exists for the existing_post
                                    existing_vote = PollVote.objects.filter(
                                        post=poll_vote.post,
                                        poll_post=existing_post
                                    ).first()

                                    if not existing_vote:
                                        # Update to point to existing_post
                                        poll_vote.poll_post = existing_post
                                        poll_vote.save()
                                        logger.debug(f"Migrated poll vote to existing post")
                                    else:
                                        # Vote already exists, delete duplicate
                                        poll_vote.delete()
                                        logger.debug(f"Deleted duplicate poll vote")
                                except Exception as e:
                                    # If there's any constraint error, just delete the vote
                                    logger.warning(f"Error migrating poll vote, deleting: {e}")
                                    poll_vote.delete()

                            # Delete duplicate post
                            old_post.delete()
                            logger.debug(f"Removed duplicate post {old_post.post_id}")

                    # Delete old profile
                    old_profile.delete()
                    logger.info(f"Deleted old profile: {old_url}")

                elif old_profile and not new_profile:
                    # Only old profile exists - update its feed URL
                    logger.info(f"Updating profile feed URL: {old_url} -> {new_url}")
                    old_profile.feed = new_url
                    old_profile.save()

                # Delete the old feed
                old_feed.delete()
                logger.info(f"Deleted old feed: {old_url}")

        elif old_feed and not new_feed:
            # Only old URL exists - update it to new URL
            logger.info(f"Feed redirect detected: {old_url} -> {new_url}")
            logger.info(f"Updating feed URL to: {new_url}")

            with transaction.atomic():
                # Update the feed URL
                old_feed.url = new_url
                old_feed.save()

                # Update all profiles pointing to old URL
                profiles_updated = Profile.objects.filter(feed=old_url).update(feed=new_url)
                logger.info(f"Updated {profiles_updated} profile(s) to new URL")

        # If new_feed exists but not old_feed, nothing to do
        # This can happen if the redirect was already processed

    except Exception as e:
        # Don't break parsing if redirect handling fails
        logger.error(f"Failed to handle redirect {old_url} -> {new_url}: {e}", exc_info=True)


def parse_org_social(url: str) -> Dict[str, Any]:
    """
    Parse an Org Social file from a URL and return structured data.

    Args:
        url: The URL to the social.org file

    Returns:
        Dictionary containing parsed metadata and posts
    """
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        # Decode content as UTF-8 explicitly to avoid encoding issues
        # when the server doesn't specify charset in Content-Type header
        content = response.content.decode('utf-8')

        # Check if URL was redirected
        final_url = response.url
        if final_url != url and response.history:
            # URL was redirected - handle the redirect
            logger.info(f"Redirect detected: {url} -> {final_url} (status: {response.history[0].status_code})")
            _handle_feed_redirect(url, final_url)
            # Use final URL for further operations
            url = final_url

        # Update last_successful_fetch if we got a 200 response
        if response.status_code == 200:
            _update_feed_last_successful_fetch(url)

    except requests.RequestException as e:
        raise Exception(f"Failed to fetch URL {url}: {str(e)}")

    # Initialize result structure
    result: Dict[str, Any] = {
        "metadata": {
            "title": "",
            "nick": "",
            "description": "",
            "avatar": "",
            "links": [],
            "follows": [],
            "contacts": [],
        },
        "posts": [],
    }

    # Parse metadata with regex (case insensitive)
    title_match = re.search(
        r"^\s*\#\+TITLE:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE
    )
    result["metadata"]["title"] = title_match.group(1).strip() if title_match else ""

    nick_match = re.search(
        r"^\s*\#\+NICK:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE
    )
    result["metadata"]["nick"] = nick_match.group(1).strip() if nick_match else ""

    description_match = re.search(
        r"^\s*\#\+DESCRIPTION:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE
    )
    result["metadata"]["description"] = (
        description_match.group(1).strip() if description_match else ""
    )

    avatar_match = re.search(r"^\s*\#\+AVATAR:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["avatar"] = avatar_match.group(1).strip() if avatar_match else ""

    # Parse multiple values
    result["metadata"]["links"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+LINK:\s*(.+)$", content, re.MULTILINE)
    ]
    result["metadata"]["contacts"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+CONTACT:\s*(.+)$", content, re.MULTILINE)
    ]

    # Parse follows (can have nickname)
    follow_matches = re.finditer(r"^\s*\#\+FOLLOW:\s*(.+)$", content, re.MULTILINE)
    for match in follow_matches:
        follow_data = match.group(1).strip()
        parts = follow_data.split()
        if len(parts) == 1:
            result["metadata"]["follows"].append({"url": parts[0], "nickname": ""})
        elif len(parts) >= 2:
            result["metadata"]["follows"].append(
                {"nickname": parts[0], "url": parts[1]}
            )

    # Parse posts - find everything after * Posts
    posts_pattern = r"\*\s+Posts\s*\n(.*)"
    posts_match = re.search(posts_pattern, content, re.DOTALL)
    if posts_match:
        posts_content = posts_match.group(1)

        # Split posts by ** headers (exactly 2 asterisks, not 3+)
        # Use negative lookahead (?!\*) to ensure we don't match *** or ****
        # Use ^ anchor to match ** only at start of line
        post_pattern = r"^\*\*(?!\*)[^\n]*\n(?::PROPERTIES:\s*\n((?::[^:\n]+:[^\n]*\n)*):END:\s*\n)?(.*?)(?=^\*\*(?!\*)|\Z)"
        post_matches = re.finditer(
            post_pattern, posts_content, re.DOTALL | re.MULTILINE
        )

        for post_match in post_matches:
            properties_text = post_match.group(1) or ""
            content_text = post_match.group(2).strip() if post_match.group(2) else ""

            post: Dict[str, Any] = {
                "id": "",
                "content": content_text,
                "properties": {},
                "mentions": [],
                "poll_options": [],
            }

            # Parse properties
            if properties_text:
                # Use [ \t]* instead of \s* to avoid capturing newlines
                prop_matches = re.finditer(r":([^:]+):[ \t]*([^\n]*)", properties_text)
                for prop_match in prop_matches:
                    prop_name = prop_match.group(1).lower().strip()
                    prop_value = prop_match.group(2).strip()
                    # Only add non-empty properties
                    if prop_value:
                        post["properties"][prop_name] = prop_value
                        if prop_name == "id":
                            post["id"] = prop_value

            # Extract mentions from content
            mention_matches = re.finditer(
                r"\[\[org-social:([^\]]+)\]\[([^\]]+)\]\]", content_text
            )
            post["mentions"] = [
                {"url": m.group(1), "nickname": m.group(2)} for m in mention_matches
            ]

            # Extract poll options from content
            poll_matches = re.finditer(
                r"^\s*-\s*\[\s*\]\s*(.+)$", content_text, re.MULTILINE
            )
            post["poll_options"] = [m.group(1).strip() for m in poll_matches]

            if post["id"]:  # Only add posts with valid ID
                result["posts"].append(post)

    return result


def parse_org_social_content(content: str) -> Dict[str, Any]:
    """
    Parse Org Social content directly and return structured data.

    Args:
        content: The raw content of the social.org file

    Returns:
        Dictionary containing parsed metadata and posts
    """
    # Initialize result structure
    result: Dict[str, Any] = {
        "metadata": {
            "title": "",
            "nick": "",
            "description": "",
            "avatar": "",
            "links": [],
            "follows": [],
            "contacts": [],
        },
        "posts": [],
    }

    # Parse metadata with regex (case insensitive)
    title_match = re.search(
        r"^\s*\#\+TITLE:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE
    )
    result["metadata"]["title"] = title_match.group(1).strip() if title_match else ""

    nick_match = re.search(
        r"^\s*\#\+NICK:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE
    )
    result["metadata"]["nick"] = nick_match.group(1).strip() if nick_match else ""

    description_match = re.search(
        r"^\s*\#\+DESCRIPTION:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE
    )
    result["metadata"]["description"] = (
        description_match.group(1).strip() if description_match else ""
    )

    avatar_match = re.search(r"^\s*\#\+AVATAR:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["avatar"] = avatar_match.group(1).strip() if avatar_match else ""

    # Parse multiple values
    result["metadata"]["links"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+LINK:\s*(.+)$", content, re.MULTILINE)
    ]
    result["metadata"]["contacts"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+CONTACT:\s*(.+)$", content, re.MULTILINE)
    ]

    # Parse follows (can have nickname)
    follow_matches = re.finditer(r"^\s*\#\+FOLLOW:\s*(.+)$", content, re.MULTILINE)
    for match in follow_matches:
        follow_data = match.group(1).strip()
        parts = follow_data.split()
        if len(parts) == 1:
            result["metadata"]["follows"].append({"url": parts[0], "nickname": ""})
        elif len(parts) >= 2:
            result["metadata"]["follows"].append(
                {"nickname": parts[0], "url": parts[1]}
            )

    # Parse posts - find everything after * Posts
    posts_pattern = r"\*\s+Posts\s*\n(.*)"
    posts_match = re.search(posts_pattern, content, re.DOTALL)
    if posts_match:
        posts_content = posts_match.group(1)

        # Split posts by ** headers (exactly 2 asterisks, not 3+)
        # Use negative lookahead (?!\*) to ensure we don't match *** or ****
        # Use ^ anchor to match ** only at start of line
        post_pattern = r"^\*\*(?!\*)[^\n]*\n(?::PROPERTIES:\s*\n((?::[^:\n]+:[^\n]*\n)*):END:\s*\n)?(.*?)(?=^\*\*(?!\*)|\Z)"
        post_matches = re.finditer(
            post_pattern, posts_content, re.DOTALL | re.MULTILINE
        )

        for post_match in post_matches:
            properties_text = post_match.group(1) or ""
            content_text = post_match.group(2).strip() if post_match.group(2) else ""

            post: Dict[str, Any] = {
                "id": "",
                "content": content_text,
                "properties": {},
                "mentions": [],
                "poll_options": [],
            }

            # Parse properties
            if properties_text:
                # Use [ \t]* instead of \s* to avoid capturing newlines
                prop_matches = re.finditer(r":([^:]+):[ \t]*([^\n]*)", properties_text)
                for prop_match in prop_matches:
                    prop_name = prop_match.group(1).lower().strip()
                    prop_value = prop_match.group(2).strip()
                    # Only add non-empty properties
                    if prop_value:
                        post["properties"][prop_name] = prop_value
                        if prop_name == "id":
                            post["id"] = prop_value

            # Extract mentions from content
            mention_matches = re.finditer(
                r"\[\[org-social:([^\]]+)\]\[([^\]]+)\]\]", content_text
            )
            post["mentions"] = [
                {"url": m.group(1), "nickname": m.group(2)} for m in mention_matches
            ]

            # Extract poll options from content
            poll_matches = re.finditer(
                r"^\s*-\s*\[\s*\]\s*(.+)$", content_text, re.MULTILINE
            )
            post["poll_options"] = [m.group(1).strip() for m in poll_matches]

            if post["id"]:  # Only add posts with valid ID
                result["posts"].append(post)

    return result


def validate_org_social_feed(url: str) -> Tuple[bool, str]:
    """
    Validate if a URL returns a valid Org Social feed.

    Args:
        url: The URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check if URL responds with 200
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return False, f"URL returned status code {response.status_code}"

        # Check if URL was redirected
        final_url = response.url
        if final_url != url and response.history:
            logger.info(f"Validation: Redirect detected: {url} -> {final_url}")
            _handle_feed_redirect(url, final_url)
            # Use final URL for validation
            url = final_url

        # Update last_successful_fetch since we got a 200 response
        _update_feed_last_successful_fetch(url)

        # Decode content as UTF-8 explicitly to avoid encoding issues
        content = response.content.decode('utf-8')

        # Check if content has basic Org Social structure
        # At minimum should have at least one #+TITLE, #+NICK, or #+DESCRIPTION (case insensitive)
        has_title = bool(
            re.search(r"^\s*\#\+TITLE:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
        )
        has_nick = bool(
            re.search(r"^\s*\#\+NICK:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
        )
        has_description = bool(
            re.search(
                r"^\s*\#\+DESCRIPTION:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE
            )
        )

        if not (has_title or has_nick or has_description):
            return (
                False,
                "Content does not appear to be a valid Org Social file (missing basic metadata)",
            )

        # Try to parse the content to ensure it's valid
        try:
            parsed_data = parse_org_social_content(content)
            # Check that we have at least some metadata
            metadata = parsed_data.get("metadata", {})
            if not any(
                [
                    metadata.get("title"),
                    metadata.get("nick"),
                    metadata.get("description"),
                ]
            ):
                return False, "Parsed content lacks required metadata"
        except Exception as e:
            return False, f"Failed to parse Org Social content: {str(e)}"

        return True, ""

    except requests.RequestException as e:
        return False, f"Failed to fetch URL: {str(e)}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"
