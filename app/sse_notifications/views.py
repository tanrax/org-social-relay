import asyncio
import json
import time
import logging
from django.http import StreamingHttpResponse
from django.views import View
from django.conf import settings

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30


def _sse_response(stream):
    response = StreamingHttpResponse(stream, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _get_redis():
    host = settings.HUEY["connection"]["host"]
    port = settings.HUEY["connection"]["port"]
    db = settings.HUEY["connection"]["db"]
    return aioredis.Redis(host=host, port=port, db=db, decode_responses=True)


class SSENotificationsView(View):
    """
    Server-Sent Events endpoint for real-time notifications.

    With ?feed=: streams notifications for a single feed.
    Without ?feed=: streams all notifications from all feeds, adding target_feed to each event.
    """

    async def get(self, request):
        feed_url = request.GET.get("feed", "").strip()
        stream = self._feed_stream(feed_url) if feed_url else self._global_stream()
        return _sse_response(stream)

    async def _feed_stream(self, feed_url):
        r = _get_redis()
        pubsub = r.pubsub()
        logger.info(f"SSE per-feed connection: {feed_url}")
        try:
            await pubsub.subscribe(f"notifications:{feed_url}")

            yield "event: connected\n"
            yield f"data: {json.dumps({'feed': feed_url, 'status': 'connected'})}\n\n"

            async for chunk in self._message_loop(pubsub):
                yield chunk

        except aioredis.RedisError as e:
            logger.error(f"Redis error for {feed_url}: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Redis connection failed'})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected error in SSE stream for {feed_url}: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
        finally:
            try:
                await pubsub.aclose()
                await r.aclose()
                logger.info(f"SSE connection closed for feed: {feed_url}")
            except Exception:
                pass

    async def _global_stream(self):
        r = _get_redis()
        pubsub = r.pubsub()
        logger.info("SSE global connection established")
        try:
            await pubsub.psubscribe("notifications:*")

            yield "event: connected\n"
            yield f"data: {json.dumps({'status': 'connected'})}\n\n"

            async for chunk in self._message_loop(pubsub, global_mode=True):
                yield chunk

        except aioredis.RedisError as e:
            logger.error(f"Redis error in global SSE stream: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Redis connection failed'})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected error in global SSE stream: {e}")
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
        finally:
            try:
                await pubsub.aclose()
                await r.aclose()
                logger.info("Global SSE connection closed")
            except Exception:
                pass

    async def _message_loop(self, pubsub, global_mode=False):
        last_heartbeat = time.time()

        while True:
            current_time = time.time()
            if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield "event: heartbeat\n"
                yield f"data: {json.dumps({'status': 'alive', 'timestamp': int(current_time)})}\n\n"
                last_heartbeat = current_time

            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )

            if message is None:
                await asyncio.sleep(0)
                continue

            msg_type = message["type"]
            is_data = (msg_type == "message") or (
                global_mode and msg_type == "pmessage"
            )
            if not is_data:
                continue

            try:
                notification_data = json.loads(message["data"])

                if global_mode:
                    channel = message["channel"]
                    notification_data["target_feed"] = channel.removeprefix(
                        "notifications:"
                    )

                yield "event: notification\n"
                yield f"data: {json.dumps(notification_data)}\n\n"

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode notification message: {e}")
            except Exception as e:
                logger.error(f"Error processing notification: {e}")
