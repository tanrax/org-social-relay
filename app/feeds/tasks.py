from huey.contrib.djhuey import periodic_task
from huey import crontab
import logging
import requests
import hashlib
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@periodic_task(crontab(hour="*/3"))  # Run every 3 hours
def discover_feeds_from_relay_nodes():
    """
    Periodic task to discover new feeds from other Org Social Relay nodes.

    This task:
    1. Fetches the list of relay nodes from the public URL
    2. Filters out our own domain to avoid self-discovery
    3. Calls each relay node's /feeds endpoint to get their registered feeds
    4. Stores newly discovered feeds in our local database
    """
    import django

    django.setup()

    from django.conf import settings
    from .models import Feed
    from .parser import validate_org_social_feed

    # URLs to fetch feeds from
    feed_sources = [
        {
            "name": "relay nodes",
            "url": "https://cdn.jsdelivr.net/gh/tanrax/org-social/org-social-relay-list.txt",
            "type": "relay_nodes",
        },
        {
            "name": "public register",
            "url": "https://raw.githubusercontent.com/tanrax/org-social/main/registers.txt",
            "type": "direct_feeds",
        },
    ]

    total_discovered = 0

    for source in feed_sources:
        logger.info(f"Fetching feeds from {source['name']}: {source['url']}")

        try:
            # Fetch the list
            response = requests.get(source["url"], timeout=5)
            response.raise_for_status()

            # The file might be empty or contain one URL per line
            urls = [line.strip() for line in response.text.split("\n") if line.strip()]

            if source["type"] == "direct_feeds":
                # For direct feeds (registers.txt), validate and add them directly
                logger.info(f"Found {len(urls)} direct feeds to validate")

                for feed_url in urls:
                    if not feed_url.strip():
                        continue

                    feed_url = feed_url.strip()

                    # Check if we already have this feed
                    if Feed.objects.filter(url=feed_url).exists():
                        continue

                    # Validate the feed before adding it
                    logger.info(f"Validating direct feed: {feed_url}")
                    is_valid, error_message = validate_org_social_feed(feed_url)

                    if not is_valid:
                        logger.warning(
                            f"Skipping invalid direct feed {feed_url}: {error_message}"
                        )
                        continue

                    # Create the feed
                    try:
                        Feed.objects.create(url=feed_url)
                        total_discovered += 1
                        logger.info(f"Added direct feed: {feed_url}")
                    except Exception as e:
                        logger.error(f"Failed to create direct feed {feed_url}: {e}")

            elif source["type"] == "relay_nodes":
                # For relay nodes, get their feeds endpoints
                relay_nodes = urls

                # Filter out our own domain to avoid self-discovery
                site_domain = settings.SITE_DOMAIN
                filtered_nodes = []
                for node_url in relay_nodes:
                    # Normalize the URL for comparison
                    normalized_node = (
                        node_url.replace("http://", "")
                        .replace("https://", "")
                        .strip("/")
                    )
                    normalized_site = site_domain.strip("/")

                    if normalized_node != normalized_site:
                        filtered_nodes.append(node_url)
                    else:
                        logger.info(f"Skipping own domain: {node_url}")

                relay_nodes = filtered_nodes

                if not relay_nodes:
                    logger.info(
                        "No relay nodes found in the list after filtering own domain"
                    )
                    continue

                logger.info(
                    f"Found {len(relay_nodes)} relay nodes to check (excluding own domain)"
                )

                for node_url in relay_nodes:
                    try:
                        # Ensure the URL has proper format
                        if not node_url.startswith(("http://", "https://")):
                            node_url = f"http://{node_url}"

                        # Call the /feeds endpoint on each relay node
                        feeds_url = f"{node_url}/feeds"
                        feeds_response = requests.get(feeds_url, timeout=10)
                        feeds_response.raise_for_status()

                        feeds_data = feeds_response.json()

                        # Check if response has expected format
                        if feeds_data.get("type") == "Success" and "data" in feeds_data:
                            feeds_list = feeds_data["data"]

                            for feed_url in feeds_list:
                                if isinstance(feed_url, str) and feed_url.strip():
                                    feed_url = feed_url.strip()

                                    # Check if we already have this feed
                                    if Feed.objects.filter(url=feed_url).exists():
                                        continue

                                    # Validate the feed before adding it
                                    logger.info(
                                        f"Validating discovered feed: {feed_url}"
                                    )
                                    is_valid, error_message = validate_org_social_feed(
                                        feed_url
                                    )

                                    if not is_valid:
                                        logger.warning(
                                            f"Skipping invalid feed {feed_url}: {error_message}"
                                        )
                                        continue

                                    # Create the feed
                                    try:
                                        Feed.objects.create(url=feed_url)
                                        total_discovered += 1
                                        logger.info(
                                            f"Discovered and validated new feed: {feed_url}"
                                        )
                                    except Exception as e:
                                        logger.error(
                                            f"Failed to create feed {feed_url}: {e}"
                                        )

                        logger.info(f"Successfully checked relay node: {node_url}")

                    except requests.RequestException as e:
                        logger.warning(
                            f"Failed to fetch feeds from relay node {node_url}: {e}"
                        )
                    except ValueError as e:
                        logger.warning(
                            f"Invalid JSON response from relay node {node_url}: {e}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Unexpected error checking relay node {node_url}: {e}"
                        )

        except requests.RequestException as e:
            logger.error(f"Failed to fetch {source['name']} from {source['url']}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing {source['name']}: {e}")

    logger.info(
        f"Feed discovery completed. Total new feeds discovered: {total_discovered}"
    )


@periodic_task(crontab(hour=0, minute=0))  # Run daily at midnight
def discover_new_feeds_from_follows():
    """
    Periodic task to discover new feeds by analyzing the feeds followed by registered users.

    This task:
    1. Gets all registered feeds from the database
    2. For each feed, fetches and parses the content
    3. Extracts URLs from #+FOLLOW: lines
    4. Adds newly discovered feeds to the database
    """
    import django

    django.setup()

    from .models import Feed, Profile, Follow
    from .parser import parse_org_social, validate_org_social_feed

    logger.info("Starting discovery of new feeds from user follows")

    # Get all registered feeds
    all_feeds = Feed.objects.all()
    total_feeds = all_feeds.count()

    if total_feeds == 0:
        logger.info("No registered feeds found")
        return

    logger.info(f"Analyzing {total_feeds} registered feeds for new follows")

    total_discovered = 0
    successful_parses = 0
    failed_parses = 0

    for feed in all_feeds:
        try:
            # Parse the org social file (may update feed URL if redirected)
            parsed_data = parse_org_social(feed.url)
            successful_parses += 1

            # Refresh feed from database (URL may have changed due to redirect)
            feed.refresh_from_db()

            # Extract follow URLs from metadata
            follows = parsed_data.get("metadata", {}).get("follows", [])

            if not follows:
                continue

            logger.info(f"Found {len(follows)} follows in {feed.url}")

            # Get or create profile for this feed
            profile = None
            try:
                metadata = parsed_data.get("metadata", {})
                content_for_hash = f"{metadata}{parsed_data.get('posts', [])}"
                content_hash = hashlib.md5(content_for_hash.encode()).hexdigest()

                profile, _ = Profile.objects.get_or_create(
                    feed=feed.url,
                    defaults={
                        "title": metadata.get("title", ""),
                        "nick": metadata.get("nick", ""),
                        "description": metadata.get("description", ""),
                        "avatar": metadata.get("avatar", ""),
                        "version": content_hash,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to create/update profile for {feed.url}: {e}")

            # Process each follow URL
            for follow_info in follows:
                follow_url = follow_info.get("url", "").strip()
                follow_nickname = follow_info.get("nickname", "").strip()

                # Basic URL validation
                if not follow_url or not follow_url.startswith(("http://", "https://")):
                    continue

                # Check if feed already exists
                existing_feed = Feed.objects.filter(url=follow_url).first()

                if not existing_feed:
                    # Validate the feed before adding it
                    logger.info(f"Validating discovered follow feed: {follow_url}")
                    is_valid, error_message = validate_org_social_feed(follow_url)

                    if not is_valid:
                        logger.warning(
                            f"Skipping invalid follow feed {follow_url}: {error_message}"
                        )
                        continue

                    # Create new feed
                    try:
                        Feed.objects.create(url=follow_url)
                        total_discovered += 1
                        logger.info(
                            f"Discovered and validated new feed from follows: {follow_url}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create feed {follow_url}: {e}")

                # Create follow relationship if we have a profile
                if profile:
                    try:
                        # Get or create the followed profile
                        followed_profile, _ = Profile.objects.get_or_create(
                            feed=follow_url,
                            defaults={
                                "title": "",
                                "nick": follow_nickname or "",
                                "description": "",
                                "avatar": "",
                                "version": "",
                            },
                        )

                        # Create follow relationship
                        follow_obj, created = Follow.objects.get_or_create(
                            follower=profile,
                            followed=followed_profile,
                            defaults={"nickname": follow_nickname},
                        )

                        if not created and follow_obj.nickname != follow_nickname:
                            # Update nickname if changed
                            follow_obj.nickname = follow_nickname
                            follow_obj.save()

                    except Exception as e:
                        logger.warning(
                            f"Failed to create follow relationship {profile.nick} -> {follow_url}: {e}"
                        )

        except requests.RequestException as e:
            failed_parses += 1
            logger.warning(f"Failed to fetch/parse feed {feed.url}: {e}")
        except Exception as e:
            failed_parses += 1
            logger.error(f"Unexpected error parsing feed {feed.url}: {e}")

    logger.info(
        f"Feed discovery from follows completed. "
        f"Analyzed: {total_feeds} feeds, "
        f"Successful: {successful_parses}, "
        f"Failed: {failed_parses}, "
        f"New feeds discovered: {total_discovered}"
    )


@periodic_task(crontab(minute="*"))  # Run every minute
def scan_feeds():
    """
    Periodic task to scan all registered feeds for new posts and profile updates.

    This task:
    1. Clears the cache so next requests after scan will get fresh data
    2. Gets all registered feeds from the database
    3. For each feed, fetches and parses the content
    4. Creates or updates Profile data with version control
    5. Creates or updates Posts with their properties
    6. Manages relationships (follows, contacts, links)

    Note: Cache is cleared AFTER scanning so that:
    - During scan: users get old cached data (complete and consistent, even if outdated)
    - After scan: cache is cleared and next requests get fresh data from database

    This ensures data consistency: users either see complete old data or complete new data,
    never a mix of both during the scanning process.
    """
    import django

    django.setup()

    from .models import (
        Feed,
        Profile,
        Post,
        ProfileLink,
        ProfileContact,
        PollOption,
        PollVote,
        Mention,
    )
    from .parser import parse_org_social
    from dateutil import parser as date_parser

    logger.info("Starting feed scanning for posts and profile updates")

    # Get all registered feeds
    all_feeds = Feed.objects.all()
    total_feeds = all_feeds.count()

    if total_feeds == 0:
        logger.info("No registered feeds found")
        return

    logger.info(f"Scanning {total_feeds} feeds for updates")

    successful_scans = 0
    failed_scans = 0
    profiles_updated = 0
    profiles_created = 0
    posts_created = 0
    posts_updated = 0

    for feed in all_feeds:
        try:
            # Parse the org social file (may update feed URL if redirected)
            parsed_data = parse_org_social(feed.url)
            successful_scans += 1

            # Refresh feed from database (URL may have changed due to redirect)
            feed.refresh_from_db()

            metadata = parsed_data.get("metadata", {})
            posts_data = parsed_data.get("posts", [])

            # Generate version hash from content
            content_for_hash = f"{metadata}{posts_data}"
            content_hash = hashlib.md5(content_for_hash.encode()).hexdigest()

            # Get or create profile
            profile, profile_created = Profile.objects.get_or_create(
                feed=feed.url,
                defaults={
                    "title": metadata.get("title", ""),
                    "nick": metadata.get("nick", ""),
                    "description": metadata.get("description", ""),
                    "avatar": metadata.get("avatar", ""),
                    "version": content_hash,
                },
            )

            if profile_created:
                profiles_created += 1
                logger.info(f"Created new profile: {profile.nick} ({feed.url})")
            else:
                # Check if content has changed by comparing version
                if profile.version != content_hash:
                    # Update profile data
                    profile.title = metadata.get("title", "")
                    profile.nick = metadata.get("nick", "")
                    profile.description = metadata.get("description", "")
                    profile.avatar = metadata.get("avatar", "")
                    profile.version = content_hash
                    profile.save()
                    profiles_updated += 1
                    logger.info(f"Updated profile: {profile.nick} ({feed.url})")

            # Update profile relationships (clear and recreate)
            profile.links.all().delete()
            profile.contacts.all().delete()

            # Create profile links
            for link_url in metadata.get("links", []):
                if link_url.strip():
                    ProfileLink.objects.create(profile=profile, url=link_url.strip())

            # Create profile contacts
            for contact in metadata.get("contacts", []):
                if contact.strip():
                    contact_parts = contact.strip().split(":", 1)
                    if len(contact_parts) == 2:
                        contact_type = contact_parts[0].strip()
                        contact_value = contact_parts[1].strip()
                        ProfileContact.objects.create(
                            profile=profile,
                            contact_type=contact_type,
                            contact_value=contact_value,
                        )

            # Process posts
            for post_data in posts_data:
                post_id = post_data.get("id", "")
                if not post_id:
                    continue

                content = post_data.get("content", "")
                properties = post_data.get("properties", {})

                # Extract group name from GROUP property
                # Format: "Emacs https://org-social-relay.andros.dev" or just "Emacs"
                # Group names can have spaces and capitals - we slugify them
                from django.conf import settings

                group_metadata = properties.get("group", "").strip()
                group_slug = ""
                if group_metadata:
                    # Extract group name (everything before the URL if present)
                    parts = group_metadata.split("http", 1)
                    raw_group_name = parts[0].strip()

                    if raw_group_name:
                        # Slugify the group name to match ENABLED_GROUPS format
                        from core.settings import slugify_group

                        group_slug = slugify_group(raw_group_name)

                        # Only save if it matches an enabled group
                        if group_slug not in settings.ENABLED_GROUPS:
                            group_slug = ""

                # Get or create post
                post, post_created = Post.objects.get_or_create(
                    profile=profile,
                    post_id=post_id,
                    defaults={
                        "content": content,
                        "language": properties.get("lang", ""),
                        "tags": properties.get("tags", ""),
                        "client": properties.get("client", ""),
                        "reply_to": properties.get("reply_to", ""),
                        "mood": properties.get("mood", ""),
                        "group": group_slug,
                        "include": properties.get("include", ""),
                        "poll_end": None,
                    },
                )

                if post_created:
                    posts_created += 1

                    # Publish notifications for NEW posts
                    from .notification_publisher import publish_notification

                    # Check if this is a reply (with or without mood/reaction)
                    if post.reply_to:
                        reply_to_parts = post.reply_to.split("#")
                        if len(reply_to_parts) == 2:
                            replied_feed_url = reply_to_parts[0]

                            # Determine if it's a reaction or a reply
                            if post.mood and post.mood.strip():
                                # It's a reaction
                                publish_notification(
                                    target_feed_url=replied_feed_url,
                                    notification_type="reaction",
                                    post_url=f"{feed.url}#{post_id}",
                                    emoji=post.mood,
                                    parent=post.reply_to,
                                )
                            else:
                                # It's a regular reply
                                publish_notification(
                                    target_feed_url=replied_feed_url,
                                    notification_type="reply",
                                    post_url=f"{feed.url}#{post_id}",
                                    parent=post.reply_to,
                                )

                    # Check if this is a boost
                    if post.include:
                        include_parts = post.include.split("#")
                        if len(include_parts) == 2:
                            boosted_feed_url = include_parts[0]
                            publish_notification(
                                target_feed_url=boosted_feed_url,
                                notification_type="boost",
                                post_url=f"{feed.url}#{post_id}",
                                boosted=post.include,
                            )
                else:
                    # Update existing post
                    post.content = content
                    post.language = properties.get("lang", "")
                    post.tags = properties.get("tags", "")
                    post.client = properties.get("client", "")
                    post.reply_to = properties.get("reply_to", "")
                    post.mood = properties.get("mood", "")
                    post.group = group_slug
                    post.include = properties.get("include", "")
                    post.save()
                    posts_updated += 1

                # Handle poll_end if present
                poll_end_str = properties.get("poll_end", "")
                if poll_end_str:
                    try:
                        poll_end_dt = date_parser.parse(poll_end_str)
                        post.poll_end = poll_end_dt
                        post.save()
                    except Exception as e:
                        logger.warning(f"Failed to parse poll_end {poll_end_str}: {e}")

                # Handle poll options
                poll_options = post_data.get("poll_options", [])
                if poll_options:
                    # Clear existing poll options
                    post.poll_options.all().delete()
                    # Create new poll options
                    for idx, option_text in enumerate(poll_options):
                        PollOption.objects.create(
                            post=post, option_text=option_text, order=idx
                        )

                # Handle poll votes
                poll_option = properties.get("poll_option", "")
                if poll_option and post.reply_to:
                    # This is a poll vote
                    try:
                        # Extract the poll post reference from reply_to
                        reply_parts = post.reply_to.split("#")
                        if len(reply_parts) == 2:
                            poll_feed_url = reply_parts[0]
                            poll_post_id = reply_parts[1]

                            # Find the poll post
                            poll_profile = Profile.objects.filter(
                                feed=poll_feed_url
                            ).first()
                            if poll_profile:
                                poll_post = Post.objects.filter(
                                    profile=poll_profile, post_id=poll_post_id
                                ).first()

                                if poll_post:
                                    # Create or update poll vote
                                    poll_vote, created = PollVote.objects.get_or_create(
                                        post=post,
                                        poll_post=poll_post,
                                        defaults={"poll_option": poll_option},
                                    )
                                    if not created:
                                        poll_vote.poll_option = poll_option
                                        poll_vote.save()
                    except Exception as e:
                        logger.warning(
                            f"Failed to process poll vote for post {post_id}: {e}"
                        )

                # Handle mentions - FIXED to detect new mentions
                mentions_data = post_data.get("mentions", [])
                if mentions_data:
                    # Get existing mentions for this post
                    existing_mentions = set(
                        post.mentions.values_list("mentioned_profile__feed", flat=True)
                    )

                    # Process each mention
                    for mention_info in mentions_data:
                        mention_url = mention_info.get("url", "").strip()
                        mention_nickname = mention_info.get("nickname", "").strip()

                        if not mention_url:
                            continue

                        # Extract the base URL (remove post ID after #)
                        base_mention_url = mention_url.split("#")[0]

                        # Try to find the mentioned profile
                        try:
                            mentioned_profile = Profile.objects.get(
                                feed=base_mention_url
                            )

                            # Only create if it doesn't exist (to detect new mentions)
                            if base_mention_url not in existing_mentions:
                                mention, mention_created = (
                                    Mention.objects.get_or_create(
                                        post=post,
                                        mentioned_profile=mentioned_profile,
                                        defaults={"nickname": mention_nickname},
                                    )
                                )

                                # If this is a NEW mention, publish notification
                                if mention_created:
                                    from .notification_publisher import (
                                        publish_notification,
                                    )

                                    publish_notification(
                                        target_feed_url=base_mention_url,
                                        notification_type="mention",
                                        post_url=f"{feed.url}#{post_id}",
                                    )

                        except Profile.DoesNotExist:
                            # The mentioned profile doesn't exist in our database
                            logger.debug(f"Mentioned profile not found: {mention_url}")
                            continue
                        except Exception as e:
                            logger.warning(
                                f"Failed to create mention for {mention_url} in post {post_id}: {e}"
                            )

            # Detect and remove deleted posts
            # Get all post IDs from the current feed scan
            current_post_ids = {post_data.get("id", "") for post_data in posts_data}
            current_post_ids.discard("")  # Remove empty IDs

            # Get all post IDs currently in database for this profile
            existing_posts = Post.objects.filter(profile=profile)
            existing_post_ids = set(existing_posts.values_list("post_id", flat=True))

            # Find posts that are in DB but not in current feed (deleted posts)
            deleted_post_ids = existing_post_ids - current_post_ids

            if deleted_post_ids:
                # Delete posts that no longer exist in the feed
                deleted_count = Post.objects.filter(
                    profile=profile, post_id__in=deleted_post_ids
                ).delete()[0]
                logger.info(
                    f"Removed {deleted_count} deleted post(s) from {feed.url}: {deleted_post_ids}"
                )

        except requests.RequestException as e:
            failed_scans += 1
            logger.warning(f"Failed to fetch/parse feed {feed.url}: {e}")
        except Exception as e:
            failed_scans += 1
            logger.error(f"Unexpected error scanning feed {feed.url}: {e}")

    logger.info(
        f"Feed scanning completed. "
        f"Scanned: {total_feeds} feeds, "
        f"Successful: {successful_scans}, "
        f"Failed: {failed_scans}, "
        f"Profiles created: {profiles_created}, "
        f"Profiles updated: {profiles_updated}, "
        f"Posts created: {posts_created}, "
        f"Posts updated: {posts_updated}"
    )

    # Update global relay metadata BEFORE clearing cache
    # This ensures the new ETag/Last-Modified are ready when cache is cleared
    from .models import RelayMetadata

    RelayMetadata.update_global_metadata()
    logger.info("Updated global relay metadata (ETag and Last-Modified)")

    # Clear cache AFTER scanning to ensure next requests get fresh data
    # This way during scan users see complete old cached data (consistent),
    # and after scan they see complete new data (also consistent)
    from django.core.cache import cache

    # Invalidate middleware cache for headers (will be recreated from DB on next request)
    cache.delete("relay_metadata_headers")

    # Clear all endpoint caches
    cache.clear()
    logger.info("Cache cleared after feed scanning - next requests will get fresh data")


def _cleanup_stale_feeds_impl():
    """
    Implementation of stale feed cleanup logic.
    This is separated from the periodic task to allow for easier testing.

    Returns:
        int: Number of feeds deleted
    """
    from .models import Feed

    logger.info("Starting cleanup of stale feeds")

    # Calculate the cutoff date (3 days ago)
    cutoff_date = timezone.now() - timedelta(days=3)

    # Find stale feeds (last_successful_fetch is older than 3 days)
    # Exclude feeds where last_successful_fetch is NULL (legacy feeds)
    stale_feeds = Feed.objects.filter(
        last_successful_fetch__lt=cutoff_date,
        last_successful_fetch__isnull=False,
    )

    stale_count = stale_feeds.count()

    if stale_count == 0:
        logger.info("No stale feeds found to clean up")
        return 0

    # Log the feeds being deleted
    logger.info(f"Found {stale_count} stale feeds to delete")
    for feed in stale_feeds[:10]:  # Log first 10 for reference
        days_since_fetch = (timezone.now() - feed.last_successful_fetch).days
        logger.info(
            f"Deleting stale feed: {feed.url} "
            f"(last successful fetch: {days_since_fetch} days ago)"
        )

    if stale_count > 10:
        logger.info(f"... and {stale_count - 10} more feeds")

    # Delete the stale feeds
    deleted_count, _ = stale_feeds.delete()

    logger.info(
        f"Stale feed cleanup completed. Deleted {deleted_count} feeds that "
        f"haven't been successfully fetched in the last 3 days"
    )

    return deleted_count


@periodic_task(crontab(day="*/3", hour=2, minute=0))  # Run every 3 days at 2 AM
def cleanup_stale_feeds():
    """
    Periodic task to clean up feeds that haven't been successfully fetched in 3 days.

    This task:
    1. Finds all feeds with last_successful_fetch older than 3 days
    2. Deletes those feeds from the database
    3. Logs the cleanup results

    Note: Feeds with last_successful_fetch = NULL are NOT deleted.
    This protects feeds that existed before the field was added.
    """
    return _cleanup_stale_feeds_impl()
