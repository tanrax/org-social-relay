import json
import time
import logging
from django.http import StreamingHttpResponse
from django.views import View
from django.conf import settings
import redis

logger = logging.getLogger(__name__)


class SSENotificationsView(View):
    """
    Server-Sent Events (SSE) endpoint for real-time notifications.

    Clients connect to this endpoint with a feed URL parameter and receive
    real-time notifications as they are published by the scan_feeds task.

    Usage:
        GET /sse/notifications/?feed=https://example.com/social.org

    Response format (Server-Sent Events):
        event: notification
        data: {"type": "mention", "post": "...", ...}

        event: heartbeat
        data: {"status": "alive"}
    """

    def get(self, request):
        feed_url = request.GET.get("feed", "").strip()

        if not feed_url:
            return StreamingHttpResponse(
                "data: "
                + json.dumps({"error": "Feed URL parameter is required"})
                + "\n\n",
                content_type="text/event-stream",
                status=400,
            )

        logger.info(f"SSE connection established for feed: {feed_url}")

        def event_stream():
            """Generator that yields SSE-formatted events"""
            try:
                # Connect to Redis
                redis_host = settings.HUEY["connection"]["host"]
                redis_port = settings.HUEY["connection"]["port"]
                redis_db = settings.HUEY["connection"]["db"]

                r = redis.Redis(
                    host=redis_host, port=redis_port, db=redis_db, decode_responses=True
                )

                # Subscribe to the feed's notification channel
                pubsub = r.pubsub()
                channel_name = f"notifications:{feed_url}"
                pubsub.subscribe(channel_name)

                logger.info(f"Subscribed to Redis channel: {channel_name}")

                # Send initial connection message
                yield "event: connected\n"
                yield f"data: {json.dumps({'feed': feed_url, 'status': 'connected'})}\n\n"

                # Keep track of last heartbeat
                last_heartbeat = time.time()
                heartbeat_interval = 30  # seconds

                # Use a while loop with get_message(timeout=1) instead of listen()
                # This allows heartbeats to be sent even when there are no messages
                while True:
                    # Send heartbeat every 30 seconds to keep connection alive
                    current_time = time.time()
                    if current_time - last_heartbeat >= heartbeat_interval:
                        yield "event: heartbeat\n"
                        yield f"data: {json.dumps({'status': 'alive', 'timestamp': int(current_time)})}\n\n"
                        last_heartbeat = current_time

                    # Check for messages with 1 second timeout
                    # This prevents blocking and allows heartbeat to run regularly
                    message = pubsub.get_message(timeout=1)

                    if message is None:
                        # No message received, continue to next iteration (will check heartbeat)
                        continue

                    # Process Redis messages
                    if message["type"] == "message":
                        try:
                            # Message data is already a JSON string from Redis
                            notification_data = json.loads(message["data"])

                            # Send notification event
                            yield "event: notification\n"
                            yield f"data: {json.dumps(notification_data)}\n\n"

                            logger.debug(
                                f"Sent notification to {feed_url}: {notification_data['type']}"
                            )

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode notification message: {e}")
                        except Exception as e:
                            logger.error(f"Error processing notification: {e}")

            except redis.RedisError as e:
                logger.error(f"Redis connection error for {feed_url}: {e}")
                yield "event: error\n"
                yield f"data: {json.dumps({'error': 'Redis connection failed'})}\n\n"
            except Exception as e:
                logger.error(f"Unexpected error in SSE stream for {feed_url}: {e}")
                yield "event: error\n"
                yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
            finally:
                try:
                    pubsub.close()
                    logger.info(f"SSE connection closed for feed: {feed_url}")
                except Exception:
                    pass

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )

        # SSE headers
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # Disable nginx buffering

        # CORS headers for cross-origin requests
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type"

        return response
