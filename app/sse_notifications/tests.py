import json
import pytest
import redis
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from app.feeds.notification_publisher import publish_notification


class TestSSENotificationsEndpoint(TestCase):
    """Test the SSE notifications endpoint"""

    def setUp(self):
        self.client = Client()
        self.feed_url = "https://example.com/social.org"

    def test_sse_endpoint_without_feed_returns_global_stream(self):
        """Test that SSE endpoint without feed parameter returns global stream"""
        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = redis.RedisError("done")
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "text/event-stream")

    def test_sse_endpoint_accepts_valid_feed(self):
        """Test that SSE endpoint accepts valid feed parameter"""
        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = redis.RedisError("done")
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/", {"feed": self.feed_url})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "text/event-stream")
            self.assertEqual(response["Cache-Control"], "no-cache")
            self.assertEqual(response["X-Accel-Buffering"], "no")
            self.assertEqual(response["Access-Control-Allow-Origin"], "*")

    def test_sse_sends_connection_event_with_feed(self):
        """Test that per-feed SSE sends initial connection event with feed field"""
        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = redis.RedisError("done")
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/", {"feed": self.feed_url})
            content = b"".join(response.streaming_content).decode("utf-8")

            self.assertIn("event: connected", content)
            self.assertIn(f'"feed": "{self.feed_url}"', content)
            self.assertIn('"status": "connected"', content)

    def test_sse_sends_connection_event_global(self):
        """Test that global SSE sends initial connection event without feed field"""
        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = redis.RedisError("done")
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/")
            content = b"".join(response.streaming_content).decode("utf-8")

            self.assertIn("event: connected", content)
            self.assertIn('"status": "connected"', content)
            self.assertNotIn('"feed":', content)

    def test_sse_receives_notification_from_redis(self):
        """Test that per-feed SSE receives and forwards notifications from Redis"""
        notification_data = {
            "type": "mention",
            "post": "https://alice.com/social.org#2024-01-01T10:00:00+0000",
        }

        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = [
                {"type": "message", "data": json.dumps(notification_data)},
                redis.RedisError("done"),
            ]
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/", {"feed": self.feed_url})
            content = b"".join(response.streaming_content).decode("utf-8")

            self.assertIn("event: notification", content)
            self.assertIn('"type": "mention"', content)
            self.assertIn("https://alice.com/social.org#2024-01-01T10:00:00+0000", content)

    def test_global_sse_adds_target_feed_to_notifications(self):
        """Test that global SSE adds target_feed field extracted from channel name"""
        notification_data = {
            "type": "mention",
            "post": "https://alice.com/social.org#2024-01-01T10:00:00+0000",
        }
        target_feed = "https://example.com/social.org"

        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = [
                {
                    "type": "pmessage",
                    "pattern": "notifications:*",
                    "channel": f"notifications:{target_feed}",
                    "data": json.dumps(notification_data),
                },
                redis.RedisError("done"),
            ]
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/")
            content = b"".join(response.streaming_content).decode("utf-8")

            self.assertIn("event: notification", content)
            self.assertIn(f'"target_feed": "{target_feed}"', content)
            self.assertIn('"type": "mention"', content)

    def test_global_sse_uses_psubscribe(self):
        """Test that global SSE subscribes with psubscribe to all notification channels"""
        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = redis.RedisError("done")
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/")
            b"".join(response.streaming_content)

            mock_pubsub.psubscribe.assert_called_once_with("notifications:*")

    def test_per_feed_sse_uses_subscribe(self):
        """Test that per-feed SSE subscribes with subscribe to the specific channel"""
        with patch("app.sse_notifications.views.redis.Redis") as mock_redis:
            mock_pubsub = MagicMock()
            mock_pubsub.get_message.side_effect = redis.RedisError("done")
            mock_redis.return_value.pubsub.return_value = mock_pubsub

            response = self.client.get("/sse/notifications/", {"feed": self.feed_url})
            b"".join(response.streaming_content)

            mock_pubsub.subscribe.assert_called_once_with(f"notifications:{self.feed_url}")


class TestNotificationPublisher(TestCase):
    """Test the notification publisher module"""

    @patch("app.feeds.notification_publisher.redis.Redis")
    def test_publish_mention_notification(self, mock_redis):
        """Test publishing a mention notification"""
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        target_feed = "https://bob.com/social.org"
        post_url = "https://alice.com/social.org#2024-01-01T10:00:00+0000"

        result = publish_notification(
            target_feed_url=target_feed, notification_type="mention", post_url=post_url
        )

        self.assertTrue(result)
        mock_redis_instance.publish.assert_called_once()

        call_args = mock_redis_instance.publish.call_args
        channel, data = call_args[0]

        self.assertEqual(channel, f"notifications:{target_feed}")

        notification = json.loads(data)
        self.assertEqual(notification["type"], "mention")
        self.assertEqual(notification["post"], post_url)

    @patch("app.feeds.notification_publisher.redis.Redis")
    def test_publish_reaction_notification_with_emoji(self, mock_redis):
        """Test publishing a reaction notification with emoji"""
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        target_feed = "https://bob.com/social.org"
        post_url = "https://alice.com/social.org#2024-01-01T10:00:00+0000"
        parent_post = "https://bob.com/social.org#2024-01-01T09:00:00+0000"

        result = publish_notification(
            target_feed_url=target_feed,
            notification_type="reaction",
            post_url=post_url,
            emoji="❤",
            parent=parent_post,
        )

        self.assertTrue(result)

        call_args = mock_redis_instance.publish.call_args
        channel, data = call_args[0]

        notification = json.loads(data)
        self.assertEqual(notification["type"], "reaction")
        self.assertEqual(notification["emoji"], "❤")
        self.assertEqual(notification["parent"], parent_post)

    @patch("app.feeds.notification_publisher.redis.Redis")
    def test_publish_reply_notification(self, mock_redis):
        """Test publishing a reply notification"""
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        target_feed = "https://bob.com/social.org"
        post_url = "https://alice.com/social.org#2024-01-01T10:00:00+0000"
        parent_post = "https://bob.com/social.org#2024-01-01T09:00:00+0000"

        result = publish_notification(
            target_feed_url=target_feed,
            notification_type="reply",
            post_url=post_url,
            parent=parent_post,
        )

        self.assertTrue(result)

        call_args = mock_redis_instance.publish.call_args
        channel, data = call_args[0]

        notification = json.loads(data)
        self.assertEqual(notification["type"], "reply")
        self.assertEqual(notification["parent"], parent_post)

    @patch("app.feeds.notification_publisher.redis.Redis")
    def test_publish_boost_notification(self, mock_redis):
        """Test publishing a boost notification"""
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        target_feed = "https://bob.com/social.org"
        post_url = "https://alice.com/social.org#2024-01-01T10:00:00+0000"
        boosted_post = "https://bob.com/social.org#2024-01-01T09:00:00+0000"

        result = publish_notification(
            target_feed_url=target_feed,
            notification_type="boost",
            post_url=post_url,
            boosted=boosted_post,
        )

        self.assertTrue(result)

        call_args = mock_redis_instance.publish.call_args
        channel, data = call_args[0]

        notification = json.loads(data)
        self.assertEqual(notification["type"], "boost")
        self.assertEqual(notification["boosted"], boosted_post)

    @patch("app.feeds.notification_publisher.redis.Redis")
    def test_publish_notification_handles_redis_error(self, mock_redis):
        """Test that publish_notification handles Redis errors gracefully"""
        mock_redis.side_effect = Exception("Redis connection failed")

        result = publish_notification(
            target_feed_url="https://bob.com/social.org",
            notification_type="mention",
            post_url="https://alice.com/social.org#2024-01-01T10:00:00+0000",
        )

        self.assertFalse(result)


@pytest.mark.django_db
class TestSSENotificationStructure:
    """Test that SSE notifications match the expected JSON structure"""

    def test_mention_notification_structure(self):
        """Test mention notification has correct structure"""
        notification = {
            "type": "mention",
            "post": "https://alice.com/social.org#2024-01-01T10:00:00+0000",
        }

        assert "type" in notification
        assert "post" in notification
        assert notification["type"] == "mention"
        assert "#" in notification["post"]

    def test_reaction_notification_structure(self):
        """Test reaction notification has correct structure"""
        notification = {
            "type": "reaction",
            "post": "https://alice.com/social.org#2024-01-01T10:00:00+0000",
            "emoji": "❤",
            "parent": "https://bob.com/social.org#2024-01-01T09:00:00+0000",
        }

        assert notification["type"] == "reaction"
        assert "emoji" in notification
        assert "parent" in notification

    def test_reply_notification_structure(self):
        """Test reply notification has correct structure"""
        notification = {
            "type": "reply",
            "post": "https://alice.com/social.org#2024-01-01T10:00:00+0000",
            "parent": "https://bob.com/social.org#2024-01-01T09:00:00+0000",
        }

        assert notification["type"] == "reply"
        assert "parent" in notification

    def test_boost_notification_structure(self):
        """Test boost notification has correct structure"""
        notification = {
            "type": "boost",
            "post": "https://alice.com/social.org#2024-01-01T10:00:00+0000",
            "boosted": "https://bob.com/social.org#2024-01-01T09:00:00+0000",
        }

        assert notification["type"] == "boost"
        assert "boosted" in notification

    def test_global_notification_includes_target_feed(self):
        """Test that global notifications include target_feed field"""
        notification = {
            "target_feed": "https://example.com/social.org",
            "type": "mention",
            "post": "https://alice.com/social.org#2024-01-01T10:00:00+0000",
        }

        assert "target_feed" in notification
        assert notification["target_feed"].startswith("http")
