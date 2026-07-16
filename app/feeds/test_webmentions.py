from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from django.test import TestCase
from django.utils import timezone

from app.feeds.models import Feed, OutgoingWebmention, Profile
from app.feeds.tasks import WEBMENTION_MAX_ATTEMPTS, _send_pending_webmentions_impl
from app.feeds.webmentions import (
    discover_webmention_endpoint,
    extract_external_urls,
    is_safe_endpoint,
    queue_webmentions_for_post,
)


class ExtractExternalUrlsTest(TestCase):
    """Test cases for URL extraction from post content."""

    def test_extract_org_link_with_description(self):
        # Given: A post containing an Org link with description
        content = "Great read: [[https://example.com/article][My article]]"

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: The linked URL is found without the description
        self.assertEqual(result, ["https://example.com/article"])

    def test_extract_org_link_without_description(self):
        # Given: A post containing a plain Org link
        content = "See [[https://example.com/article]] for details"

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: The linked URL is found
        self.assertEqual(result, ["https://example.com/article"])

    def test_extract_bare_url(self):
        # Given: A post containing a bare URL
        content = "Check https://example.com/post and tell me"

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: The bare URL is found
        self.assertEqual(result, ["https://example.com/post"])

    def test_bare_url_trailing_punctuation_stripped(self):
        # Given: A bare URL wrapped in punctuation
        content = "Nice one (https://example.com/post). Really!"

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: Trailing punctuation is not part of the URL
        self.assertEqual(result, ["https://example.com/post"])

    def test_url_with_query_string_and_fragment_is_preserved(self):
        # Given: A URL with query string and fragment
        content = "See https://example.com/post?id=1&lang=en#section-2"

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: Query string and fragment are kept intact
        self.assertEqual(result, ["https://example.com/post?id=1&lang=en#section-2"])

    def test_org_social_mentions_are_ignored(self):
        # Given: A post with an Org Social mention and a normal link
        content = (
            "Hi [[org-social:https://other.example/social.org][bob]] look at "
            "[[https://example.com/article][this]]"
        )

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: Only the normal link is found, the mention is skipped
        self.assertEqual(result, ["https://example.com/article"])

    def test_duplicate_urls_are_deduplicated(self):
        # Given: A post repeating the same URL as Org link and bare URL
        content = (
            "https://example.com/a and again [[https://example.com/a][same]] "
            "plus https://example.com/b"
        )

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: Each URL appears once, in order of appearance
        self.assertEqual(result, ["https://example.com/a", "https://example.com/b"])

    def test_empty_or_missing_content_returns_no_urls(self):
        # Given: Empty and missing content
        # When: URLs are extracted
        # Then: No URLs are found and nothing breaks
        self.assertEqual(extract_external_urls(""), [])
        self.assertEqual(extract_external_urls(None), [])

    def test_non_http_schemes_are_ignored(self):
        # Given: A post with non-http(s) URIs only
        content = "Write to mailto:me@example.com or ftp://example.com/file"

        # When: URLs are extracted
        result = extract_external_urls(content)

        # Then: Nothing is extracted
        self.assertEqual(result, [])


def _mock_response(
    url="https://example.com/article",
    headers=None,
    body=b"",
    encoding="utf-8",
):
    """Build a minimal mock of a streamed requests.Response."""
    response = Mock()
    response.url = url
    response.headers = headers or {}
    response.encoding = encoding
    response.raw = Mock()
    response.raw.read = Mock(return_value=body)
    return response


class DiscoverWebmentionEndpointTest(TestCase):
    """Test cases for endpoint discovery per the W3C spec."""

    @patch("app.feeds.webmentions.requests.get")
    def test_link_header_discovery(self, mock_get):
        # Given: A target advertising its endpoint in the HTTP Link header
        mock_get.return_value = _mock_response(
            headers={
                "Link": '<https://example.com/wm>; rel="webmention"',
                "Content-Type": "text/html",
            }
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: The Link header endpoint is returned
        self.assertEqual(endpoint, "https://example.com/wm")

    @patch("app.feeds.webmentions.requests.get")
    def test_link_header_takes_precedence_over_html(self, mock_get):
        # Given: A target with endpoints both in the Link header and the HTML
        mock_get.return_value = _mock_response(
            headers={
                "Link": '<https://example.com/header-wm>; rel="webmention"',
                "Content-Type": "text/html",
            },
            body=b'<link rel="webmention" href="https://example.com/html-wm">',
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: The Link header wins, as the spec requires
        self.assertEqual(endpoint, "https://example.com/header-wm")

    @patch("app.feeds.webmentions.requests.get")
    def test_link_header_with_multiple_rels(self, mock_get):
        # Given: A Link header whose rel lists several values
        mock_get.return_value = _mock_response(
            headers={
                "Link": '<https://example.com/wm>; rel="webmention somethingelse"',
                "Content-Type": "text/html",
            }
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: The webmention rel is still recognized
        self.assertEqual(endpoint, "https://example.com/wm")

    @patch("app.feeds.webmentions.requests.get")
    def test_html_link_element_discovery(self, mock_get):
        # Given: A target advertising a relative endpoint in a <link> element
        mock_get.return_value = _mock_response(
            headers={"Content-Type": "text/html; charset=utf-8"},
            body=b'<html><head><link rel="webmention" href="/wm"></head></html>',
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: The relative href is resolved against the target
        self.assertEqual(endpoint, "https://example.com/wm")

    @patch("app.feeds.webmentions.requests.get")
    def test_html_anchor_element_discovery(self, mock_get):
        # Given: A target advertising its endpoint in an <a> element
        mock_get.return_value = _mock_response(
            headers={"Content-Type": "text/html"},
            body=b'<body><a rel="webmention" href="https://wm.example.org/ep">wm</a></body>',
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: The anchor endpoint is returned
        self.assertEqual(endpoint, "https://wm.example.org/ep")

    @patch("app.feeds.webmentions.requests.get")
    def test_first_element_in_document_order_wins(self, mock_get):
        # Given: Both an <a> and a <link> endpoint, the <a> appearing first
        mock_get.return_value = _mock_response(
            headers={"Content-Type": "text/html"},
            body=(
                b'<a rel="webmention" href="/first">a</a>'
                b'<link rel="webmention" href="/second">'
            ),
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: The first element in document order wins
        self.assertEqual(endpoint, "https://example.com/first")

    @patch("app.feeds.webmentions.requests.get")
    def test_empty_href_resolves_to_page_url(self, mock_get):
        # Given: An endpoint advertised with an empty href
        mock_get.return_value = _mock_response(
            url="https://example.com/article",
            headers={"Content-Type": "text/html"},
            body=b'<link rel="webmention" href="">',
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: It resolves to the page URL itself
        self.assertEqual(endpoint, "https://example.com/article")

    @patch("app.feeds.webmentions.requests.get")
    def test_relative_endpoint_resolved_after_redirect(self, mock_get):
        # Given: A target that redirected and advertises a relative endpoint
        mock_get.return_value = _mock_response(
            url="https://final.example.com/page",
            headers={"Content-Type": "text/html"},
            body=b'<link rel="webmention" href="wm-endpoint">',
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: The endpoint resolves against the final URL after redirects
        self.assertEqual(endpoint, "https://final.example.com/wm-endpoint")

    @patch("app.feeds.webmentions.requests.get")
    def test_no_endpoint_returns_none(self, mock_get):
        # Given: A target without any webmention endpoint
        mock_get.return_value = _mock_response(
            headers={"Content-Type": "text/html"},
            body=b"<html><body>No webmention here</body></html>",
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: No endpoint is found
        self.assertIsNone(endpoint)

    @patch("app.feeds.webmentions.requests.get")
    def test_non_html_content_without_link_header_returns_none(self, mock_get):
        # Given: A non-HTML target without a Link header
        mock_get.return_value = _mock_response(
            headers={"Content-Type": "application/pdf"},
            body=b"%PDF-1.4",
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/doc.pdf")

        # Then: No endpoint is found and the body is never parsed as HTML
        self.assertIsNone(endpoint)

    @patch("app.feeds.webmentions.requests.get")
    def test_rel_without_webmention_is_ignored(self, mock_get):
        # Given: A page whose only <link> has an unrelated rel
        mock_get.return_value = _mock_response(
            headers={"Content-Type": "text/html"},
            body=b'<link rel="stylesheet" href="/style.css">',
        )

        # When: The endpoint is discovered
        endpoint = discover_webmention_endpoint("https://example.com/article")

        # Then: No endpoint is found
        self.assertIsNone(endpoint)


class IsSafeEndpointTest(TestCase):
    """Test cases for endpoint safety checks (spec section 4.3)."""

    def test_rejects_non_http_scheme(self):
        # Given: Endpoints with non-http(s) schemes
        # When: They are checked
        # Then: They are rejected
        self.assertFalse(is_safe_endpoint("ftp://example.com/wm"))
        self.assertFalse(is_safe_endpoint("file:///etc/passwd"))

    @patch("app.feeds.webmentions.socket.getaddrinfo")
    def test_rejects_loopback(self, mock_getaddrinfo):
        # Given: An endpoint resolving to a loopback address
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("127.0.0.1", 80))]

        # When/Then: It is rejected
        self.assertFalse(is_safe_endpoint("http://localhost/wm"))

    @patch("app.feeds.webmentions.socket.getaddrinfo")
    def test_rejects_private_address(self, mock_getaddrinfo):
        # Given: An endpoint resolving to a private address
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.10", 80))]

        # When/Then: It is rejected
        self.assertFalse(is_safe_endpoint("https://internal.example.com/wm"))

    @patch("app.feeds.webmentions.socket.getaddrinfo")
    def test_accepts_public_address(self, mock_getaddrinfo):
        # Given: An endpoint resolving to a public address
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]

        # When/Then: It is accepted
        self.assertTrue(is_safe_endpoint("https://example.com/wm"))

    @patch("app.feeds.webmentions.socket.getaddrinfo")
    def test_rejects_unresolvable_host(self, mock_getaddrinfo):
        # Given: An endpoint whose host does not resolve
        import socket as socket_module

        mock_getaddrinfo.side_effect = socket_module.gaierror()

        # When/Then: It is rejected
        self.assertFalse(is_safe_endpoint("https://nope.invalid/wm"))


class QueueWebmentionsForPostTest(TestCase):
    """Test cases for queueing outgoing webmentions during feed scans."""

    def setUp(self):
        """Set up test fixtures."""
        self.feed_url = "https://example.com/social.org"
        self.feed = Feed.objects.create(url=self.feed_url)
        self.profile = Profile.objects.create(
            feed=self.feed_url, nick="alice", title="Alice"
        )
        self.post_id = "2026-01-01T10:00:00+00:00"

    def test_queues_external_urls_as_pending(self):
        # Given: A post linking to an external article
        content = "I wrote about it: [[https://blog.example.org/post][my post]]"

        # When: Webmentions are queued for the post
        queued = queue_webmentions_for_post(self.profile, self.post_id, content)

        # Then: One pending webmention exists with the post as source
        self.assertEqual(queued, 1)
        webmention = OutgoingWebmention.objects.get()
        self.assertEqual(webmention.source, f"{self.feed_url}#{self.post_id}")
        self.assertEqual(webmention.target, "https://blog.example.org/post")
        self.assertEqual(webmention.status, OutgoingWebmention.STATUS_PENDING)

    def test_rescanning_same_post_does_not_duplicate(self):
        # Given: A post whose webmention was already queued
        content = "Look at https://blog.example.org/post please"
        queue_webmentions_for_post(self.profile, self.post_id, content)

        # When: The same post is queued again (rescan)
        queued = queue_webmentions_for_post(self.profile, self.post_id, content)

        # Then: Nothing new is queued
        self.assertEqual(queued, 0)
        self.assertEqual(OutgoingWebmention.objects.count(), 1)

    def test_rescan_does_not_reset_sent_status(self):
        # Given: A webmention already delivered for the post
        content = "Look at https://blog.example.org/post please"
        queue_webmentions_for_post(self.profile, self.post_id, content)
        OutgoingWebmention.objects.update(status=OutgoingWebmention.STATUS_SENT)

        # When: The same post is queued again (rescan)
        queue_webmentions_for_post(self.profile, self.post_id, content)

        # Then: The delivered webmention keeps its sent status
        self.assertEqual(
            OutgoingWebmention.objects.get().status, OutgoingWebmention.STATUS_SENT
        )

    def test_edited_post_queues_only_new_urls(self):
        # Given: A post whose original link was already delivered
        queue_webmentions_for_post(
            self.profile, self.post_id, "First link https://blog.example.org/a"
        )
        OutgoingWebmention.objects.update(status=OutgoingWebmention.STATUS_SENT)

        # When: The post is edited adding a second link
        queued = queue_webmentions_for_post(
            self.profile,
            self.post_id,
            "First link https://blog.example.org/a and https://blog.example.org/b",
        )

        # Then: Only the added link is queued, the delivered one is untouched
        self.assertEqual(queued, 1)
        self.assertEqual(OutgoingWebmention.objects.count(), 2)
        self.assertEqual(
            OutgoingWebmention.objects.get(target="https://blog.example.org/a").status,
            OutgoingWebmention.STATUS_SENT,
        )

    def test_registered_feeds_are_excluded(self):
        # Given: A post linking to a registered Org Social feed and to an article
        Feed.objects.create(url="https://friend.example.org/social.org")
        content = (
            "Read https://friend.example.org/social.org#2026-01-01T00:00:00+00:00 "
            "and https://blog.example.org/post"
        )

        # When: Webmentions are queued for the post
        queued = queue_webmentions_for_post(self.profile, self.post_id, content)

        # Then: Only the article is queued, the feed link is handled natively
        self.assertEqual(queued, 1)
        self.assertEqual(
            OutgoingWebmention.objects.get().target, "https://blog.example.org/post"
        )

    def test_own_feed_is_excluded(self):
        # Given: A post linking to the author's own feed
        content = f"Self reference {self.feed_url}#2025-12-31T00:00:00+00:00"

        # When: Webmentions are queued for the post
        queued = queue_webmentions_for_post(self.profile, self.post_id, content)

        # Then: Nothing is queued
        self.assertEqual(queued, 0)

    def test_post_without_urls_queues_nothing(self):
        # Given: A post with no URLs at all
        content = "Just text"

        # When: Webmentions are queued for the post
        queued = queue_webmentions_for_post(self.profile, self.post_id, content)

        # Then: Nothing is queued
        self.assertEqual(queued, 0)
        self.assertEqual(OutgoingWebmention.objects.count(), 0)


class ScanFeedsWebmentionIntegrationTest(TestCase):
    """Integration tests: scan_feeds queues webmentions exactly once."""

    def setUp(self):
        """Set up test fixtures."""
        self.feed_url = "https://example.com/social.org"
        self.feed = Feed.objects.create(url=self.feed_url)

    def _parsed_feed(self, content):
        return {
            "metadata": {"title": "Alice", "nick": "alice"},
            "posts": [
                {
                    "id": "2026-01-01T10:00:00+00:00",
                    "content": content,
                    "properties": {},
                    "mentions": [],
                    "poll_options": [],
                }
            ],
        }

    @patch("app.feeds.parser.parse_org_social")
    def test_new_post_queues_webmention_once(self, mock_parse):
        from app.feeds.tasks import scan_feeds

        # Given: A feed with a new post linking to an article
        mock_parse.return_value = self._parsed_feed(
            "Article: https://blog.example.org/post"
        )

        # When: The feed is scanned twice without changes
        scan_feeds.call_local()
        first_scan_count = OutgoingWebmention.objects.count()
        scan_feeds.call_local()

        # Then: Exactly one webmention is queued, the rescan adds nothing
        self.assertEqual(first_scan_count, 1)
        self.assertEqual(OutgoingWebmention.objects.count(), 1)

    @patch("app.feeds.parser.parse_org_social")
    def test_edited_post_queues_only_added_link(self, mock_parse):
        from app.feeds.tasks import scan_feeds

        # Given: A scanned feed whose post links to one article
        mock_parse.return_value = self._parsed_feed(
            "Article: https://blog.example.org/a"
        )
        scan_feeds.call_local()
        self.assertEqual(OutgoingWebmention.objects.count(), 1)

        # When: The post is edited adding a second link and rescanned
        mock_parse.return_value = self._parsed_feed(
            "Article: https://blog.example.org/a and https://blog.example.org/b"
        )
        scan_feeds.call_local()

        # Then: Only the added link produced a new webmention
        self.assertEqual(OutgoingWebmention.objects.count(), 2)
        targets = set(OutgoingWebmention.objects.values_list("target", flat=True))
        self.assertEqual(
            targets, {"https://blog.example.org/a", "https://blog.example.org/b"}
        )


class SendPendingWebmentionsTest(TestCase):
    """Test cases for the delivery task."""

    def _create_webmention(self, **kwargs):
        defaults = {
            "source": "https://example.com/social.org#2026-01-01T10:00:00+00:00",
            "target": "https://blog.example.org/post",
        }
        defaults.update(kwargs)
        return OutgoingWebmention.objects.create(**defaults)

    @patch("app.feeds.webmentions.is_safe_endpoint", return_value=True)
    @patch("app.feeds.webmentions.send_webmention")
    @patch("app.feeds.webmentions.discover_webmention_endpoint")
    def test_pending_webmention_is_sent(self, mock_discover, mock_send, _mock_safe):
        # Given: A pending webmention whose target accepts it with 202
        mock_discover.return_value = "https://blog.example.org/wm"
        mock_send.return_value = 202
        webmention = self._create_webmention()

        # When: The delivery task runs
        counters = _send_pending_webmentions_impl()

        # Then: The webmention is delivered once and marked as sent
        self.assertEqual(counters["sent"], 1)
        webmention.refresh_from_db()
        self.assertEqual(webmention.status, OutgoingWebmention.STATUS_SENT)
        self.assertEqual(webmention.endpoint, "https://blog.example.org/wm")
        self.assertEqual(webmention.response_code, 202)
        self.assertEqual(webmention.attempts, 1)
        mock_send.assert_called_once_with(
            "https://blog.example.org/wm", webmention.source, webmention.target
        )

    @patch("app.feeds.webmentions.discover_webmention_endpoint")
    def test_target_without_endpoint_is_marked_permanently(self, mock_discover):
        # Given: A pending webmention whose target has no endpoint
        mock_discover.return_value = None
        webmention = self._create_webmention()

        # When: The delivery task runs
        counters = _send_pending_webmentions_impl()

        # Then: The webmention is marked permanently as no_endpoint
        self.assertEqual(counters["no_endpoint"], 1)
        webmention.refresh_from_db()
        self.assertEqual(webmention.status, OutgoingWebmention.STATUS_NO_ENDPOINT)

        # Then: A later run never fetches that target again
        mock_discover.reset_mock()
        _send_pending_webmentions_impl()
        mock_discover.assert_not_called()

    @patch("app.feeds.webmentions.is_safe_endpoint", return_value=False)
    @patch("app.feeds.webmentions.discover_webmention_endpoint")
    def test_unsafe_endpoint_is_rejected(self, mock_discover, _mock_safe):
        # Given: A pending webmention whose endpoint points to loopback
        mock_discover.return_value = "http://127.0.0.1/wm"
        webmention = self._create_webmention()

        # When: The delivery task runs
        counters = _send_pending_webmentions_impl()

        # Then: Nothing is sent and the webmention is discarded
        self.assertEqual(counters["no_endpoint"], 1)
        webmention.refresh_from_db()
        self.assertEqual(webmention.status, OutgoingWebmention.STATUS_NO_ENDPOINT)

    @patch("app.feeds.webmentions.discover_webmention_endpoint")
    def test_network_error_marks_failed_and_retries_later(self, mock_discover):
        # Given: A pending webmention whose target is unreachable
        mock_discover.side_effect = requests.RequestException("boom")
        webmention = self._create_webmention()

        # When: The delivery task runs
        counters = _send_pending_webmentions_impl()

        # Then: The webmention is marked failed with one attempt
        self.assertEqual(counters["failed"], 1)
        webmention.refresh_from_db()
        self.assertEqual(webmention.status, OutgoingWebmention.STATUS_FAILED)
        self.assertEqual(webmention.attempts, 1)

        # Then: Within the backoff window it is skipped
        mock_discover.reset_mock()
        _send_pending_webmentions_impl()
        mock_discover.assert_not_called()

        # Then: After the backoff window it is retried
        webmention.last_attempt_at = timezone.now() - timedelta(hours=2)
        webmention.save()
        mock_discover.side_effect = None
        mock_discover.return_value = None
        _send_pending_webmentions_impl()
        webmention.refresh_from_db()
        self.assertEqual(webmention.status, OutgoingWebmention.STATUS_NO_ENDPOINT)

    @patch("app.feeds.webmentions.discover_webmention_endpoint")
    def test_max_attempts_reached_stops_retrying(self, mock_discover):
        # Given: A webmention that already exhausted its attempts long ago
        self._create_webmention(
            status=OutgoingWebmention.STATUS_FAILED,
            attempts=WEBMENTION_MAX_ATTEMPTS,
            last_attempt_at=timezone.now() - timedelta(days=30),
        )

        # When: The delivery task runs
        counters = _send_pending_webmentions_impl()

        # Then: It is never processed again
        self.assertEqual(counters, {"sent": 0, "no_endpoint": 0, "failed": 0})
        mock_discover.assert_not_called()

    @patch("app.feeds.webmentions.is_safe_endpoint", return_value=True)
    @patch("app.feeds.webmentions.send_webmention")
    @patch("app.feeds.webmentions.discover_webmention_endpoint")
    def test_http_error_response_marks_failed(
        self, mock_discover, mock_send, _mock_safe
    ):
        # Given: A pending webmention whose endpoint answers HTTP 500
        mock_discover.return_value = "https://blog.example.org/wm"
        mock_send.return_value = 500
        webmention = self._create_webmention()

        # When: The delivery task runs
        counters = _send_pending_webmentions_impl()

        # Then: The webmention is marked failed keeping the endpoint for retry
        self.assertEqual(counters["failed"], 1)
        webmention.refresh_from_db()
        self.assertEqual(webmention.status, OutgoingWebmention.STATUS_FAILED)
        self.assertEqual(webmention.response_code, 500)
        self.assertEqual(webmention.endpoint, "https://blog.example.org/wm")
