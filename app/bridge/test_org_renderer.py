from django.test import TestCase

from app.bridge.org_renderer import render_profile_org
from app.feeds.models import Post, Profile, ProfileLink


class RenderProfileOrgTest(TestCase):
    """Test cases for the virtual social.org renderer."""

    def setUp(self):
        # Given: A bridged profile with a link and two posts
        self.profile = Profile.objects.create(
            feed="http://localhost:8080/bridge/activitypub/@alice@m.example/",
            title="Alice in Wonderland",
            nick="alice",
            description="Just a test account",
            avatar="https://m.example/avatar.png",
            version="v1",
        )
        ProfileLink.objects.create(profile=self.profile, url="https://m.example/@alice")
        Post.objects.create(
            profile=self.profile,
            post_id="2025-05-01T10:00:00+00:00",
            content="Hello world",
            created_at="2025-05-01T10:00:00+00:00",
        )
        Post.objects.create(
            profile=self.profile,
            post_id="2025-05-02T10:00:00+00:00",
            content="Second post",
            tags="emacs org",
            language="en",
            created_at="2025-05-02T10:00:00+00:00",
        )

    def test_renders_global_metadata(self):
        # When: The profile is rendered
        result = render_profile_org(self.profile, self.profile.posts.all())

        # Then: All global metadata lines are present
        self.assertIn("#+TITLE: Alice in Wonderland\n", result)
        self.assertIn("#+NICK: alice\n", result)
        self.assertIn("#+DESCRIPTION: Just a test account\n", result)
        self.assertIn("#+AVATAR: https://m.example/avatar.png\n", result)
        self.assertIn("#+LINK: https://m.example/@alice\n", result)

    def test_renders_posts_section_with_properties(self):
        # When: The profile is rendered oldest post first
        posts = self.profile.posts.order_by("created_at")
        result = render_profile_org(self.profile, posts)

        # Then: Posts appear under * Posts with their properties
        self.assertIn("* Posts\n", result)
        self.assertIn("** 2025-05-01T10:00:00+00:00\n", result)
        self.assertIn("** 2025-05-02T10:00:00+00:00\n", result)
        self.assertIn(":TAGS: emacs org\n", result)
        self.assertIn(":LANG: en\n", result)
        self.assertIn("Hello world\n", result)
        # And: The first post comes before the second
        self.assertLess(
            result.index("2025-05-01T10:00:00+00:00"),
            result.index("2025-05-02T10:00:00+00:00"),
        )

    def test_nick_with_spaces_is_sanitized(self):
        # Given: A profile whose nick contains spaces
        self.profile.nick = "alice cooper"

        # When: The profile is rendered
        result = render_profile_org(self.profile, [])

        # Then: The nick has no spaces
        self.assertIn("#+NICK: alice_cooper\n", result)

    def test_metadata_never_spans_multiple_lines(self):
        # Given: A profile description containing newlines
        self.profile.description = "line one\nline two"

        # When: The profile is rendered
        result = render_profile_org(self.profile, [])

        # Then: The description is collapsed into a single line
        self.assertIn("#+DESCRIPTION: line one line two\n", result)

    def test_post_content_headlines_are_escaped(self):
        # Given: A post whose content looks like an Org Social headline
        Post.objects.create(
            profile=self.profile,
            post_id="2025-05-03T10:00:00+00:00",
            content="** 2030-01-01T00:00:00+00:00\ninjected",
            created_at="2025-05-03T10:00:00+00:00",
        )

        # When: The profile is rendered
        result = render_profile_org(
            self.profile, self.profile.posts.order_by("created_at")
        )

        # Then: The injected headline is escaped
        self.assertIn(" ** 2030-01-01T00:00:00+00:00\n", result)
        self.assertNotIn("\n** 2030-01-01T00:00:00+00:00\n", result)

    def test_empty_optional_metadata_is_omitted(self):
        # Given: A profile with no description, avatar nor links
        profile = Profile.objects.create(
            feed="http://localhost:8080/bridge/rss/?url=x",
            title="Bare",
            nick="bare",
            version="v1",
        )

        # When: The profile is rendered
        result = render_profile_org(profile, [])

        # Then: Optional lines are not present
        self.assertNotIn("#+DESCRIPTION:", result)
        self.assertNotIn("#+AVATAR:", result)
        self.assertNotIn("#+LINK:", result)
