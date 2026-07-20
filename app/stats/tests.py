from datetime import datetime, timezone as dt_timezone

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from app.feeds.models import Feed, Follow, Post, Profile


class StatsViewTest(TestCase):
    """Test cases for the StatsView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.stats_url = "/stats/"
        cache.clear()

        self.profile1 = Profile.objects.create(
            feed="https://alice.org/social.org",
            title="Alice",
            nick="alice",
        )
        self.profile2 = Profile.objects.create(
            feed="https://bob.org/social.org",
            title="Bob",
            nick="bob",
        )

    def tearDown(self):
        cache.clear()

    def _create_post(self, profile, post_id, **kwargs):
        """Create a post whose created_at matches its RFC 3339 post_id"""
        created_at = datetime.fromisoformat(post_id).astimezone(dt_timezone.utc)
        return Post.objects.create(
            profile=profile,
            post_id=post_id,
            created_at=created_at,
            **kwargs,
        )

    def test_empty_database_returns_empty_stats(self):
        """Test GET /stats/ with no posts returns empty years and zeroed globals."""
        # Given: No posts, feeds or follows exist (only two profiles)

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: The response is successful with empty monthly data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])
        self.assertEqual(response.data["data"]["years"], {})
        self.assertEqual(
            response.data["data"]["global"],
            {
                "registered_feeds": 0,
                "total_accounts": 2,
                "total_posts": 0,
                "total_follows": 0,
                "active_groups": 0,
            },
        )
        self.assertIn("generated_at", response.data["meta"])
        self.assertEqual(
            response.data["_links"]["self"],
            {"href": "/stats/", "method": "GET"},
        )

    def test_post_types_are_disjoint_and_sum_to_total(self):
        """Test each post type is counted once and the sum matches total_posts."""
        # Given: One post of each type in the same month
        self._create_post(self.profile1, "2025-03-01T10:00:00+00:00", content="Plain")
        self._create_post(
            self.profile1,
            "2025-03-02T10:00:00+00:00",
            content="A reply with text",
            reply_to="https://bob.org/social.org#2025-03-01T09:00:00+00:00",
        )
        self._create_post(
            self.profile1,
            "2025-03-03T10:00:00+00:00",
            content="",
            reply_to="https://bob.org/social.org#2025-03-01T09:00:00+00:00",
            mood="😄",
        )
        self._create_post(
            self.profile1,
            "2025-03-04T10:00:00+00:00",
            content="",
            include="https://bob.org/social.org#2025-03-01T09:00:00+00:00",
        )

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: Each type is counted once and the four counters sum to total
        month = response.data["data"]["years"]["2025"]["03"]
        self.assertEqual(month["total_posts"], 4)
        self.assertEqual(month["posts"], 1)
        self.assertEqual(month["replies"], 1)
        self.assertEqual(month["reactions"], 1)
        self.assertEqual(month["boosts"], 1)
        self.assertEqual(
            month["posts"] + month["replies"] + month["reactions"] + month["boosts"],
            month["total_posts"],
        )

    def test_reaction_requires_mood_and_empty_content(self):
        """Test replies with mood and text count as replies, not reactions."""
        # Given: A reply with mood but real content, and a reaction with
        # whitespace-only content
        self._create_post(
            self.profile1,
            "2025-05-01T10:00:00+00:00",
            content="Great post!",
            reply_to="https://bob.org/social.org#2025-04-30T09:00:00+00:00",
            mood="🔥",
        )
        self._create_post(
            self.profile2,
            "2025-05-02T10:00:00+00:00",
            content="  \n ",
            reply_to="https://alice.org/social.org#2025-04-30T09:00:00+00:00",
            mood="👍",
        )

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: Only the empty-content reply counts as a reaction
        month = response.data["data"]["years"]["2025"]["05"]
        self.assertEqual(month["replies"], 1)
        self.assertEqual(month["reactions"], 1)

    def test_group_messages_and_polls_are_transversal(self):
        """Test group messages and polls also count in their base type."""
        # Given: A poll and a reply inside a group
        self._create_post(
            self.profile1,
            "2025-06-01T10:00:00+00:00",
            content="Cat or dog?",
            poll_end=datetime(2025, 6, 10, tzinfo=dt_timezone.utc),
        )
        self._create_post(
            self.profile2,
            "2025-06-02T10:00:00+00:00",
            content="I agree",
            reply_to="https://alice.org/social.org#2025-06-01T09:00:00+00:00",
            group="emacs",
        )

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: The poll counts as post and the group reply counts as reply
        month = response.data["data"]["years"]["2025"]["06"]
        self.assertEqual(month["total_posts"], 2)
        self.assertEqual(month["posts"], 1)
        self.assertEqual(month["replies"], 1)
        self.assertEqual(month["polls"], 1)
        self.assertEqual(month["group_messages"], 1)

    def test_active_accounts_counts_distinct_profiles(self):
        """Test active_accounts counts each profile once per month."""
        # Given: Two posts from the same profile and one from another
        self._create_post(self.profile1, "2025-07-01T10:00:00+00:00", content="One")
        self._create_post(self.profile1, "2025-07-02T10:00:00+00:00", content="Two")
        self._create_post(self.profile2, "2025-07-03T10:00:00+00:00", content="Three")

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: Only two distinct accounts are active
        month = response.data["data"]["years"]["2025"]["07"]
        self.assertEqual(month["active_accounts"], 2)
        self.assertEqual(month["total_posts"], 3)

    def test_posts_are_grouped_by_year_and_month(self):
        """Test posts land in the year/month of their ID with padded keys."""
        # Given: Posts in different months and years
        self._create_post(self.profile1, "2024-12-15T10:00:00+00:00", content="Dec")
        self._create_post(self.profile1, "2025-01-15T10:00:00+00:00", content="Jan")
        self._create_post(self.profile2, "2025-01-20T10:00:00+00:00", content="Jan 2")

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: Months are grouped under their year with zero-padded keys
        years = response.data["data"]["years"]
        self.assertEqual(sorted(years.keys()), ["2024", "2025"])
        self.assertEqual(years["2024"]["12"]["total_posts"], 1)
        self.assertEqual(years["2025"]["01"]["total_posts"], 2)

    def test_global_counters(self):
        """Test global counters reflect feeds, accounts, follows and groups."""
        # Given: Feeds, follows and posts in two different groups
        Feed.objects.create(url="https://alice.org/social.org")
        Feed.objects.create(url="https://bob.org/social.org")
        Feed.objects.create(url="https://carol.org/social.org")
        Follow.objects.create(follower=self.profile1, followed=self.profile2)
        self._create_post(
            self.profile1, "2025-08-01T10:00:00+00:00", content="Hi", group="emacs"
        )
        self._create_post(
            self.profile1, "2025-08-02T10:00:00+00:00", content="Hi", group="emacs"
        )
        self._create_post(
            self.profile2, "2025-08-03T10:00:00+00:00", content="Hi", group="org-mode"
        )

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: Global counters match the created records
        self.assertEqual(
            response.data["data"]["global"],
            {
                "registered_feeds": 3,
                "total_accounts": 2,
                "total_posts": 3,
                "total_follows": 1,
                "active_groups": 2,
            },
        )

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        }
    )
    def test_response_is_cached(self):
        """Test the response is cached until the cache is cleared."""
        # Given: A first request that populates the cache (DEBUG uses
        # DummyCache, so a real in-memory backend is forced here)
        self._create_post(self.profile1, "2025-09-01T10:00:00+00:00", content="One")
        first = self.client.get(self.stats_url)
        self.assertEqual(first.data["data"]["global"]["total_posts"], 1)

        # When: A new post arrives without clearing the cache
        self._create_post(self.profile1, "2025-09-02T10:00:00+00:00", content="Two")
        cached = self.client.get(self.stats_url)

        # Then: The cached response is returned until the cache is cleared
        self.assertEqual(cached.data["data"]["global"]["total_posts"], 1)
        cache.clear()
        fresh = self.client.get(self.stats_url)
        self.assertEqual(fresh.data["data"]["global"]["total_posts"], 2)

    def test_bridge_feeds_do_not_count_in_stats(self):
        """Test bridge profiles, posts, feeds and follows are excluded."""
        # Given: A real feed with posts and a bridge with feed, posts and follow
        Feed.objects.create(url="https://alice.org/social.org")
        self._create_post(self.profile1, "2025-08-01T10:00:00+00:00", content="Hi")

        bridge_profile = Profile.objects.create(
            feed=(
                "https://relay.org-social.org/bridge/rss/"
                "?url=https%3A%2F%2Frss.arxiv.org%2Frss%2Fquant-ph"
            ),
            title="quant-ph updates on arXiv.org",
            nick="quant-ph_updates_on_arXiv_org",
        )
        Feed.objects.create(url=bridge_profile.feed)
        Follow.objects.create(follower=self.profile1, followed=bridge_profile)
        for second in range(3):
            self._create_post(
                bridge_profile,
                f"2025-08-02T04:00:0{second}+00:00",
                content="Bridged paper",
                group="physics",
            )

        # When: We request the stats
        response = self.client.get(self.stats_url)

        # Then: Global counters only reflect the real feed and its post
        self.assertEqual(
            response.data["data"]["global"],
            {
                "registered_feeds": 1,
                "total_accounts": 2,
                "total_posts": 1,
                "total_follows": 0,
                "active_groups": 0,
            },
        )

        # Then: The monthly breakdown ignores the bridged posts
        month = response.data["data"]["years"]["2025"]["08"]
        self.assertEqual(month["total_posts"], 1)
        self.assertEqual(month["active_accounts"], 1)
