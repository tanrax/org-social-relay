from django.test import TestCase

from app.bridge.store import store_bridge_data
from app.feeds.models import Post, Profile

FEED_URL = "http://localhost:8080/bridge/activitypub/@alice@m.example/"


def _data(posts=None, nick="alice", title="Alice"):
    return {
        "metadata": {
            "title": title,
            "nick": nick,
            "description": "Bio",
            "avatar": "https://m.example/avatar.png",
            "link": "https://m.example/@alice",
        },
        "posts": posts if posts is not None else [],
    }


def _post(post_id, content, tags=""):
    return {"id": post_id, "content": content, "tags": tags, "language": ""}


class StoreBridgeDataTest(TestCase):
    """Test cases for storing normalized bridge data."""

    def test_creates_profile_with_posts_and_link(self):
        # Given: Normalized data with two posts
        data = _data(
            posts=[
                _post("2025-05-01T10:00:00+00:00", "First"),
                _post("2025-05-02T10:00:00+00:00", "Second", tags="emacs"),
            ]
        )

        # When: The data is stored
        profile = store_bridge_data(FEED_URL, data)

        # Then: Profile, posts and link exist in the database
        self.assertEqual(profile.feed, FEED_URL)
        self.assertEqual(profile.nick, "alice")
        self.assertEqual(profile.posts.count(), 2)
        self.assertEqual(
            list(profile.links.values_list("url", flat=True)),
            ["https://m.example/@alice"],
        )
        post = profile.posts.get(post_id="2025-05-02T10:00:00+00:00")
        self.assertEqual(post.tags, "emacs")

    def test_nick_with_spaces_is_sanitized(self):
        # Given: Metadata with a nick containing spaces
        data = _data(nick="alice cooper")

        # When: The data is stored
        profile = store_bridge_data(FEED_URL, data)

        # Then: The nick has no spaces
        self.assertEqual(profile.nick, "alice_cooper")

    def test_unchanged_data_is_not_rewritten(self):
        # Given: Data already stored once
        data = _data(posts=[_post("2025-05-01T10:00:00+00:00", "First")])
        profile = store_bridge_data(FEED_URL, data)
        version = profile.version

        # When: The exact same data is stored again
        profile_again = store_bridge_data(FEED_URL, data)

        # Then: The version hash does not change and posts are intact
        self.assertEqual(profile_again.version, version)
        self.assertEqual(profile_again.posts.count(), 1)

    def test_changed_post_content_is_updated(self):
        # Given: A stored post whose content changes at the origin
        post_id = "2025-05-01T10:00:00+00:00"
        store_bridge_data(FEED_URL, _data(posts=[_post(post_id, "Original")]))

        # When: The new version is stored
        store_bridge_data(FEED_URL, _data(posts=[_post(post_id, "Edited")]))

        # Then: The post content is updated in place
        profile = Profile.objects.get(feed=FEED_URL)
        self.assertEqual(profile.posts.get(post_id=post_id).content, "Edited")
        self.assertEqual(profile.posts.count(), 1)

    def test_posts_deleted_at_origin_are_removed_within_window(self):
        # Given: Three stored posts
        store_bridge_data(
            FEED_URL,
            _data(
                posts=[
                    _post("2025-05-01T10:00:00+00:00", "A"),
                    _post("2025-05-02T10:00:00+00:00", "B"),
                    _post("2025-05-03T10:00:00+00:00", "C"),
                ]
            ),
        )

        # When: The origin no longer returns the middle post
        store_bridge_data(
            FEED_URL,
            _data(
                posts=[
                    _post("2025-05-01T10:00:00+00:00", "A"),
                    _post("2025-05-03T10:00:00+00:00", "C"),
                ]
            ),
        )

        # Then: The deleted post is removed
        profile = Profile.objects.get(feed=FEED_URL)
        ids = set(profile.posts.values_list("post_id", flat=True))
        self.assertEqual(
            ids, {"2025-05-01T10:00:00+00:00", "2025-05-03T10:00:00+00:00"}
        )

    def test_posts_older_than_fetched_window_are_preserved(self):
        # Given: An old post stored from a previous, deeper fetch
        store_bridge_data(
            FEED_URL, _data(posts=[_post("2025-01-01T10:00:00+00:00", "Old")])
        )

        # When: A later fetch only returns newer posts
        store_bridge_data(
            FEED_URL, _data(posts=[_post("2025-05-01T10:00:00+00:00", "New")])
        )

        # Then: The old post outside the fetched window survives
        profile = Profile.objects.get(feed=FEED_URL)
        ids = set(profile.posts.values_list("post_id", flat=True))
        self.assertEqual(
            ids, {"2025-01-01T10:00:00+00:00", "2025-05-01T10:00:00+00:00"}
        )

    def test_no_webmentions_are_queued_for_bridged_posts(self):
        # Given: A bridged post containing an external link
        from app.feeds.models import OutgoingWebmention

        data = _data(
            posts=[
                _post(
                    "2025-05-01T10:00:00+00:00",
                    "Look at [[https://external.example/page][this]]",
                )
            ]
        )

        # When: The data is stored
        store_bridge_data(FEED_URL, data)

        # Then: No outgoing webmention is created
        self.assertEqual(OutgoingWebmention.objects.count(), 0)

    def test_post_created_at_comes_from_post_id(self):
        # Given: A post with a known timestamp ID
        store_bridge_data(
            FEED_URL, _data(posts=[_post("2025-05-01T10:00:00+00:00", "A")])
        )

        # When: The post is read back
        post = Post.objects.get(post_id="2025-05-01T10:00:00+00:00")

        # Then: created_at matches the ID timestamp
        self.assertEqual(post.created_at.isoformat(), "2025-05-01T10:00:00+00:00")
