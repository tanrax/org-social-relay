import json
from unittest.mock import patch

from django.test import SimpleTestCase

from app.bridge.activitypub import (
    MAX_POSTS,
    fetch_account,
    normalize_handle,
)
from app.bridge.fetching import BridgeError

WEBFINGER_URL = (
    "https://mastodon.example/.well-known/webfinger"
    "?resource=acct%3Aalice%40mastodon.example"
)
ACTOR_URL = "https://mastodon.example/users/alice"
OUTBOX_URL = "https://mastodon.example/users/alice/outbox"
OUTBOX_PAGE_URL = "https://mastodon.example/users/alice/outbox?page=true"


def _note_item(published, content, **extra):
    note = {"type": "Note", "published": published, "content": content}
    note.update(extra)
    return {"type": "Create", "object": note}


def _default_responses():
    return {
        WEBFINGER_URL: {
            "links": [
                {"rel": "http://webfinger.net/rel/profile-page"},
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": ACTOR_URL,
                },
            ]
        },
        ACTOR_URL: {
            "preferredUsername": "alice",
            "name": "Alice",
            "summary": "<p>My <strong>bio</strong></p>",
            "icon": {"url": "https://mastodon.example/avatar.png"},
            "url": "https://mastodon.example/@alice",
            "outbox": OUTBOX_URL,
        },
        OUTBOX_URL: {"first": OUTBOX_PAGE_URL},
        OUTBOX_PAGE_URL: {
            "orderedItems": [
                _note_item(
                    "2025-05-02T10:00:00Z",
                    "<p>Second post</p>",
                    tag=[{"type": "Hashtag", "name": "#emacs"}],
                    contentMap={"es": "<p>Segundo post</p>"},
                ),
                _note_item(
                    "2025-05-01T18:00:00Z",
                    "<p>Reply post</p>",
                    inReplyTo="https://other.example/notes/1",
                ),
                {"type": "Announce", "object": "https://other.example/notes/2"},
                _note_item(
                    "2025-05-01T10:00:00Z",
                    "<p>First post</p>",
                    summary="Spoilers inside",
                    attachment=[
                        {
                            "type": "Document",
                            "url": "https://mastodon.example/media/cat.png",
                        }
                    ],
                ),
            ]
        },
    }


def _fake_safe_get(responses):
    def fake(url, accept=None):
        if url not in responses:
            raise BridgeError(f"Unexpected URL in test: {url}")
        return json.dumps(responses[url]).encode()

    return fake


class NormalizeHandleTest(SimpleTestCase):
    """Test cases for handle normalization."""

    def test_valid_handle_is_lowercased_and_stripped(self):
        # Given: A handle with leading @, capitals and spaces around
        raw = "  @Alice@Mastodon.Example  "

        # When: It is normalized
        result = normalize_handle(raw)

        # Then: The canonical lowercase form is returned
        self.assertEqual(result, "alice@mastodon.example")

    def test_handle_without_at_prefix_is_accepted(self):
        # Given: A handle without the leading @
        # When: It is normalized
        # Then: It is valid
        self.assertEqual(
            normalize_handle("alice@mastodon.example"), "alice@mastodon.example"
        )

    def test_invalid_handles_return_none(self):
        # Given: Handles missing parts or with invalid characters
        invalid = [
            "alice",
            "alice@",
            "@instance-only",
            "alice@nodots",
            "ali ce@mastodon.example",
            "alice@mastodon.example/evil",
            "",
            None,
        ]

        # When/Then: None of them normalize
        for handle in invalid:
            self.assertIsNone(normalize_handle(handle), handle)


class FetchAccountTest(SimpleTestCase):
    """Test cases for the ActivityPub account fetcher."""

    def test_fetches_profile_metadata_from_actor(self):
        # Given: A reachable account with actor metadata
        responses = _default_responses()

        # When: The account is fetched
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            result = fetch_account("alice", "mastodon.example")

        # Then: Metadata comes from the actor document
        self.assertEqual(result["actor_url"], ACTOR_URL)
        self.assertEqual(result["outbox_url"], OUTBOX_URL)
        self.assertEqual(result["metadata"]["title"], "Alice")
        self.assertEqual(result["metadata"]["nick"], "alice")
        self.assertEqual(result["metadata"]["description"], "My *bio*")
        self.assertEqual(
            result["metadata"]["avatar"], "https://mastodon.example/avatar.png"
        )
        self.assertEqual(result["metadata"]["link"], "https://mastodon.example/@alice")

    def test_only_top_level_notes_become_posts(self):
        # Given: An outbox with a note, a reply and an announce
        responses = _default_responses()

        # When: The account is fetched
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            result = fetch_account("alice", "mastodon.example")

        # Then: Only the two top-level notes are bridged
        self.assertEqual(len(result["posts"]), 2)
        ids = [post["id"] for post in result["posts"]]
        self.assertEqual(
            ids, ["2025-05-02T10:00:00+00:00", "2025-05-01T10:00:00+00:00"]
        )

    def test_post_carries_tags_language_cw_and_attachments(self):
        # Given: Notes with hashtag, contentMap, summary and attachment
        responses = _default_responses()

        # When: The account is fetched
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            result = fetch_account("alice", "mastodon.example")

        # Then: The second post has tags and language
        tagged = result["posts"][0]
        self.assertEqual(tagged["tags"], "emacs")
        self.assertEqual(tagged["language"], "es")
        # And: The first post has the CW line and the attachment link
        with_cw = result["posts"][1]
        self.assertTrue(with_cw["content"].startswith("CW: Spoilers inside"))
        self.assertIn("[[https://mastodon.example/media/cat.png]]", with_cw["content"])

    def test_notes_without_valid_date_are_skipped(self):
        # Given: An outbox with a dateless note and a naive-date note
        responses = _default_responses()
        responses[OUTBOX_PAGE_URL] = {
            "orderedItems": [
                {"type": "Create", "object": {"type": "Note", "content": "<p>x</p>"}},
                _note_item("2025-05-01T10:00:00", "<p>naive date</p>"),
                _note_item("2025-05-01T10:00:00Z", "<p>good</p>"),
            ]
        }

        # When: The account is fetched
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            result = fetch_account("alice", "mastodon.example")

        # Then: Only the note with a timezone-aware date survives
        self.assertEqual(len(result["posts"]), 1)
        self.assertEqual(result["posts"][0]["content"], "good")

    def test_outbox_pagination_is_followed_up_to_max_posts(self):
        # Given: An outbox split into two pages with many notes
        page_two_url = "https://mastodon.example/users/alice/outbox?page=2"
        responses = _default_responses()
        responses[OUTBOX_PAGE_URL] = {
            "orderedItems": [
                _note_item(f"2025-05-02T10:00:{second:02d}Z", "<p>a</p>")
                for second in range(30)
            ],
            "next": page_two_url,
        }
        responses[page_two_url] = {
            "orderedItems": [
                _note_item(f"2025-05-01T10:00:{second:02d}Z", "<p>b</p>")
                for second in range(30)
            ]
        }

        # When: The account is fetched
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            result = fetch_account("alice", "mastodon.example")

        # Then: Both pages are read but capped at MAX_POSTS
        self.assertEqual(len(result["posts"]), MAX_POSTS)

    def test_webfinger_without_actor_link_raises(self):
        # Given: A WebFinger response without a self link
        responses = _default_responses()
        responses[WEBFINGER_URL] = {"links": [{"rel": "other"}]}

        # When/Then: Fetching raises a BridgeError
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            with self.assertRaises(BridgeError):
                fetch_account("alice", "mastodon.example")

    def test_invalid_json_raises_bridge_error(self):
        # Given: A server answering HTML instead of JSON
        def fake(url, accept=None):
            return b"<html>not json</html>"

        # When/Then: Fetching raises a BridgeError
        with patch("app.bridge.activitypub.safe_get", side_effect=fake):
            with self.assertRaises(BridgeError):
                fetch_account("alice", "mastodon.example")

    def test_actor_without_outbox_returns_profile_without_posts(self):
        # Given: An actor document without an outbox
        responses = _default_responses()
        del responses[ACTOR_URL]["outbox"]

        # When: The account is fetched
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            result = fetch_account("alice", "mastodon.example")

        # Then: The profile exists with no posts
        self.assertEqual(result["posts"], [])
        self.assertEqual(result["outbox_url"], "")

    def test_outbox_with_inline_items_needs_no_extra_page(self):
        # Given: An outbox embedding orderedItems directly
        responses = _default_responses()
        responses[OUTBOX_URL] = {
            "orderedItems": [_note_item("2025-05-01T10:00:00Z", "<p>inline</p>")]
        }

        # When: The account is fetched
        with patch(
            "app.bridge.activitypub.safe_get",
            side_effect=_fake_safe_get(responses),
        ):
            result = fetch_account("alice", "mastodon.example")

        # Then: The inline note is bridged
        self.assertEqual(len(result["posts"]), 1)
        self.assertEqual(result["posts"][0]["content"], "inline")
