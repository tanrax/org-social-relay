import json
import time
import logging
from django.http import StreamingHttpResponse
from django.views import View
from django.conf import settings
import redis

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30


def _sse_headers(response):
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _get_redis_pubsub():
    redis_host = settings.HUEY["connection"]["host"]
    redis_port = settings.HUEY["connection"]["port"]
    redis_db = settings.HUEY["connection"]["db"]
    r = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
    return r.pubsub()


class SSENotificationsView(View):
    """
    Server-Sent Events endpoint for real-time notifications.

    With ?feed=: streams notifications for a single feed.
    Without ?feed=: streams all notifications from all feeds, adding target_feed to each event.
    """

    def get(self, request):
        feed_url = request.GET.get("feed", "").strip()

        stream = self._feed_stream(feed_url) if feed_url else self._global_stream()
        return _sse_headers(StreamingHttpResponse(stream, content_type="text/event-stream"))

    def _feed_stream(self, feed_url):
        logger.info(f"SSE per-feed connection: {feed_url}")
        try:
            pubsub = _get_redis_pubsub()
            pubsub.subscribe(f"notifications:{feed_url}")

            yield "event: connected\n"
            yield f"data: {json.dumps({'feed': feed_url, 'status': 'connected'})}\n\n"

            yield from self._message_loop(pubsub, feed_url=feed_url)

        except redis.RedisError as e:
            logger.error(f"Redis error for {feed_url}: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Redis connection failed'})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected error in SSE stream for {feed_url}: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

    def _global_stream(self):
        logger.info("SSE global connection established")
        try:
            pubsub = _get_redis_pubsub()
            pubsub.psubscribe("notifications:*")

            yield "event: connected\n"
            yield f"data: {json.dumps({'status': 'connected'})}\n\n"

            yield from self._message_loop(pubsub, global_mode=True)

        except redis.RedisError as e:
            logger.error(f"Redis error in global SSE stream: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Redis connection failed'})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected error in global SSE stream: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

    def _message_loop(self, pubsub, feed_url=None, global_mode=False):
        last_heartbeat = time.time()

        while True:
            current_time = time.time()
            if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield "event: heartbeat\n"
                yield f"data: {json.dumps({'status': 'alive', 'timestamp': int(current_time)})}\n\n"
                last_heartbeat = current_time

            message = pubsub.get_message(timeout=1)
            if message is None:
                continue

            msg_type = message["type"]
            is_data = (msg_type == "message") or (global_mode and msg_type == "pmessage")
            if not is_data:
                continue

            try:
                notification_data = json.loads(message["data"])

                if global_mode:
                    channel = message["channel"]
                    target_feed = channel.removeprefix("notifications:")
                    notification_data["target_feed"] = target_feed

                yield "event: notification\n"
                yield f"data: {json.dumps(notification_data)}\n\n"

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode notification message: {e}")
            except Exception as e:
                logger.error(f"Error processing notification: {e}")
