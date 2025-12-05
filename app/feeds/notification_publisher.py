"""
Notification publisher for real-time SSE notifications.

This module handles publishing notifications to Redis Pub/Sub channels
so that SSE clients can receive real-time updates.
"""

import json
import logging
import redis
from django.conf import settings

logger = logging.getLogger(__name__)


def get_redis_connection():
    """Get a Redis connection using Huey settings."""
    try:
        redis_host = settings.HUEY["connection"]["host"]
        redis_port = settings.HUEY["connection"]["port"]
        redis_db = settings.HUEY["connection"]["db"]

        return redis.Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
    except Exception as e:
        logger.error(f"Failed to create Redis connection: {e}")
        return None


def publish_notification(target_feed_url, notification_type, post_url, **extra_data):
    """
    Publish a notification to a feed's Redis Pub/Sub channel.

    Args:
        target_feed_url: URL of the feed that should receive the notification
        notification_type: Type of notification ("mention", "reply", "reaction", "boost")
        post_url: Full post URL (feed_url#post_id) that triggered the notification
        **extra_data: Additional data to include in the notification (e.g., emoji, parent)

    Returns:
        bool: True if published successfully, False otherwise
    """
    try:
        r = get_redis_connection()
        if not r:
            return False

        # Build notification payload
        notification = {"type": notification_type, "post": post_url, **extra_data}

        # Publish to the target feed's channel
        channel = f"notifications:{target_feed_url}"
        r.publish(channel, json.dumps(notification))

        logger.debug(f"Published {notification_type} notification to {target_feed_url}")
        return True

    except Exception as e:
        logger.error(f"Failed to publish notification: {e}")
        return False
