import os
import tempfile
from unittest.mock import Mock, patch
from django.test import TestCase


class OrgSocialParserTest(TestCase):
    """Test cases for the Org Social parser using Given/When/Then structure."""

    def test_parse_complete_org_social_file(self):
        """Test parsing a complete org social file with all features."""
        # Given: A complete org social file content
        test_file_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "social-test.org"
        )

        with open(test_file_path, "r", encoding="utf-8") as f:
            test_content = f.read()

        # Create a temporary file to serve via HTTP (mock URL)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".org", delete=False, encoding="utf-8"
        ) as tmp_file:
            tmp_file.write(test_content)
            tmp_file.flush()

            # When: We parse the org social content
            from app.feeds.parser import parse_org_social_content

            result = parse_org_social_content(test_content)

            # Then: All metadata should be correctly parsed
            self.assertEqual(result["metadata"]["title"], "Terron's Daily Adventures")
            self.assertEqual(result["metadata"]["nick"], "terron_cat")
            self.assertEqual(
                result["metadata"]["description"],
                "🐱 Orange tabby cat | 🐟 Tuna enthusiast | 🛏️ Professional napper | 🪟 Window watcher | 🧶 Ball of yarn destroyer | 😺 Purr machine",
            )
            self.assertEqual(
                result["metadata"]["avatar"],
                "https://example.com/cats/terron-avatar.jpg",
            )

            # Then: Links should be parsed correctly
            self.assertEqual(len(result["metadata"]["links"]), 2)
            self.assertIn("https://terron-cat.meow", result["metadata"]["links"])
            self.assertIn(
                "https://instagram.com/terron_the_orange", result["metadata"]["links"]
            )

            # Then: Contacts should be parsed correctly
            self.assertEqual(len(result["metadata"]["contacts"]), 2)
            self.assertIn("mailto:meow@terron-cat.meow", result["metadata"]["contacts"])
            self.assertIn(
                "https://mastodon.social/@terron_cat", result["metadata"]["contacts"]
            )

            # Then: Follows should be parsed correctly
            self.assertEqual(len(result["metadata"]["follows"]), 3)
            self.assertEqual(
                result["metadata"]["follows"][0]["nickname"], "whiskers_tabby"
            )
            self.assertEqual(
                result["metadata"]["follows"][0]["url"],
                "https://whiskers.example.com/social.org",
            )

            # Then: Posts should be parsed correctly
            self.assertEqual(len(result["posts"]), 17)

            # Clean up
            os.unlink(tmp_file.name)

    def test_parse_post_with_properties(self):
        """Test parsing a post with various properties."""
        # Given: An org social content with a post containing properties
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-15T09:30:00+0100
:LANG: en
:TAGS: django python web-development
:CLIENT: org-social.el
:MOOD: 🚀
:END:

This is a test post with properties.
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The post should have correct properties
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        self.assertEqual(post["id"], "2025-01-15T09:30:00+0100")
        self.assertEqual(post["properties"]["lang"], "en")
        self.assertEqual(post["properties"]["tags"], "django python web-development")
        self.assertEqual(post["properties"]["client"], "org-social.el")
        self.assertEqual(post["properties"]["mood"], "🚀")
        self.assertEqual(post["content"], "This is a test post with properties.")

    def test_parse_post_with_mentions(self):
        """Test parsing a post with mentions."""
        # Given: An org social content with mentions
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-20T13:15:00+0100
:END:

Hello [[org-social:https://bob.example.com/social.org][bob]] and [[org-social:https://alice.dev/social.org][alice]]!
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The mentions should be extracted correctly
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        self.assertEqual(len(post["mentions"]), 2)
        self.assertEqual(
            post["mentions"][0]["url"], "https://bob.example.com/social.org"
        )
        self.assertEqual(post["mentions"][0]["nickname"], "bob")
        self.assertEqual(post["mentions"][1]["url"], "https://alice.dev/social.org")
        self.assertEqual(post["mentions"][1]["nickname"], "alice")

    def test_parse_poll_post(self):
        """Test parsing a poll post with options."""
        # Given: An org social content with a poll
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-19T11:30:00+0100
:POLL_END: 2025-01-26T11:30:00+0100
:END:

What's your favorite Python web framework?

- [ ] Django
- [ ] FastAPI
- [ ] Flask
- [ ] Pyramid
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The poll options should be extracted correctly
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        self.assertEqual(post["properties"]["poll_end"], "2025-01-26T11:30:00+0100")
        self.assertEqual(len(post["poll_options"]), 4)
        self.assertIn("Django", post["poll_options"])
        self.assertIn("FastAPI", post["poll_options"])
        self.assertIn("Flask", post["poll_options"])
        self.assertIn("Pyramid", post["poll_options"])

    def test_parse_reply_post(self):
        """Test parsing a reply post."""
        # Given: An org social content with a reply
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-20T13:15:00+0100
:REPLY_TO: https://bob.example.com/social.org#2025-01-19T10:00:00+0100
:MOOD: 👍
:END:

Totally agree with your thoughts on code reviews!
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The reply should be parsed correctly
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        self.assertEqual(
            post["properties"]["reply_to"],
            "https://bob.example.com/social.org#2025-01-19T10:00:00+0100",
        )
        self.assertEqual(post["properties"]["mood"], "👍")

    def test_parse_poll_vote_post(self):
        """Test parsing a poll vote post."""
        # Given: An org social content with a poll vote
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-23T09:20:00+0100
:REPLY_TO: https://bob.example.com/social.org#2025-01-19T10:00:00+0100
:POLL_OPTION: Django
:END:

Django all the way! The admin interface saves me hours.
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The poll vote should be parsed correctly
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        self.assertEqual(
            post["properties"]["reply_to"],
            "https://bob.example.com/social.org#2025-01-19T10:00:00+0100",
        )
        self.assertEqual(post["properties"]["poll_option"], "Django")

    def test_parse_empty_content(self):
        """Test parsing empty or invalid content."""
        # Given: Empty content
        content = ""

        # When: We parse the empty content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: Result should have empty but valid structure
        self.assertEqual(result["metadata"]["title"], "")
        self.assertEqual(result["metadata"]["nick"], "")
        self.assertEqual(len(result["posts"]), 0)

    def test_parse_follow_with_and_without_nickname(self):
        """Test parsing follow entries with and without nicknames."""
        # Given: An org social content with different follow formats
        content = """#+TITLE: Test
#+NICK: test_user
#+FOLLOW: bob_coder https://bob.example.com/social.org
#+FOLLOW: https://charlie.dev/social.org

* Posts
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: Both follow formats should be parsed correctly
        self.assertEqual(len(result["metadata"]["follows"]), 2)

        # Follow with nickname
        self.assertEqual(result["metadata"]["follows"][0]["nickname"], "bob_coder")
        self.assertEqual(
            result["metadata"]["follows"][0]["url"],
            "https://bob.example.com/social.org",
        )

        # Follow without nickname
        self.assertEqual(result["metadata"]["follows"][1]["nickname"], "")
        self.assertEqual(
            result["metadata"]["follows"][1]["url"], "https://charlie.dev/social.org"
        )

    def test_parse_multiline_post_content(self):
        """Test parsing posts with multiline content."""
        # Given: An org social content with multiline post
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-15T09:30:00+0100
:END:

This is the first line.

This is the second paragraph with some text.

- This is a list item
- Another list item
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The multiline content should be preserved
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        self.assertIn("This is the first line.", post["content"])
        self.assertIn("This is the second paragraph", post["content"])
        self.assertIn("- This is a list item", post["content"])
        self.assertIn("- Another list item", post["content"])

    def test_parse_post_with_subsections(self):
        """Test parsing posts with level 3+ org headings (subsections)."""
        # Given: An org social content with posts containing *** and **** headings
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-15T09:30:00+0100
:LANG: en
:TAGS: tutorial
:END:

Introduction to the topic

*** Section 1: Getting Started
This is content under a level 3 heading.

**** Subsection 1.1: Installation
Deep nested content under level 4 heading.

*** Section 2: Advanced Usage
More content under another level 3 heading.

***** Even deeper
Content with 5 asterisks.

**
:PROPERTIES:
:ID: 2025-01-15T10:00:00+0100
:END:

Second post without subsections.
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: Should parse 2 posts correctly
        self.assertEqual(len(result["posts"]), 2)

        # First post should contain all subsection content
        post1 = result["posts"][0]
        self.assertEqual(post1["id"], "2025-01-15T09:30:00+0100")
        self.assertIn("Introduction to the topic", post1["content"])
        self.assertIn("*** Section 1: Getting Started", post1["content"])
        self.assertIn("This is content under a level 3 heading", post1["content"])
        self.assertIn("**** Subsection 1.1: Installation", post1["content"])
        self.assertIn("Deep nested content under level 4 heading", post1["content"])
        self.assertIn("*** Section 2: Advanced Usage", post1["content"])
        self.assertIn("More content under another level 3 heading", post1["content"])
        self.assertIn("***** Even deeper", post1["content"])
        self.assertIn("Content with 5 asterisks", post1["content"])

        # Second post should only contain its own content
        post2 = result["posts"][1]
        self.assertEqual(post2["id"], "2025-01-15T10:00:00+0100")
        self.assertEqual(post2["content"], "Second post without subsections.")
        self.assertNotIn("Section 1", post2["content"])
        self.assertNotIn("Section 2", post2["content"])

    def test_parse_empty_properties_not_captured(self):
        """Test that empty properties are not captured and don't interfere with other properties."""
        # Given: An org social content with empty properties (the bug scenario)
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-11-01T13:29:21+0100
:TAGS:
:CLIENT: org-social.el
:REPLY_TO: https://andros.dev/static/social.org#2025-11-01T11:12:51+0100
:MOOD:
:POLL_OPTION: Continue improving org-social.el
:END:

"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The post should be parsed correctly
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        # Then: Non-empty properties should be captured correctly
        self.assertEqual(post["properties"]["id"], "2025-11-01T13:29:21+0100")
        self.assertEqual(post["properties"]["client"], "org-social.el")
        self.assertEqual(
            post["properties"]["reply_to"],
            "https://andros.dev/static/social.org#2025-11-01T11:12:51+0100",
        )
        self.assertEqual(
            post["properties"]["poll_option"], "Continue improving org-social.el"
        )

        # Then: Empty properties should NOT be in the result
        self.assertNotIn("tags", post["properties"])
        self.assertNotIn("mood", post["properties"])

        # Then: Verify that MOOD did not capture POLL_OPTION value (the bug)
        # If the bug exists, mood would be ":POLL_OPTION: Continue improving org-social.el"
        if "mood" in post["properties"]:
            self.assertNotIn("POLL_OPTION", post["properties"]["mood"])

    def test_parse_properties_regex_does_not_capture_newlines(self):
        """Regression test: Verify the property regex doesn't capture newlines.

        This test specifically validates that the regex pattern uses [ \\t]* instead of \\s*
        to avoid capturing newlines after property names. This was the root cause of the
        bug where :MOOD: would capture the entire next line including :POLL_OPTION:.
        """
        # Given: An org social content with properties on consecutive lines
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-01T10:00:00+00:00
:FIRST_EMPTY:
:SECOND_PROPERTY: This should not be captured by FIRST_EMPTY
:ANOTHER_EMPTY:
:THIRD_PROPERTY: This should not be captured by ANOTHER_EMPTY
:END:

Test content
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: Properties should be parsed correctly
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        # Then: Non-empty properties should exist
        self.assertEqual(
            post["properties"]["second_property"],
            "This should not be captured by FIRST_EMPTY",
        )
        self.assertEqual(
            post["properties"]["third_property"],
            "This should not be captured by ANOTHER_EMPTY",
        )

        # Then: Empty properties should NOT exist in the parsed result
        self.assertNotIn("first_empty", post["properties"])
        self.assertNotIn("another_empty", post["properties"])

        # Then: Critical regression check - no property should contain a colon at the start
        # (which would indicate it captured the next property)
        for key, value in post["properties"].items():
            self.assertFalse(
                value.startswith(":"),
                f"Property '{key}' has value starting with colon: '{value}'. "
                f"This indicates the regex is capturing the next property.",
            )

    def test_parse_emoji_with_skin_tone_utf8(self):
        """Test parsing emojis with skin tone modifiers in UTF-8 encoding.

        This test validates that emojis with skin tone modifiers (like 🙌🏻)
        are correctly parsed and stored in UTF-8 encoding, not double-encoded.
        """
        # Given: An org social content with emoji containing skin tone modifier
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-11-13T12:05:35+0100
:REPLY_TO: https://example.com/social.org#2025-11-13T10:00:00+0100
:MOOD: 🙌🏻
:END:

Great work!
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: The emoji should be correctly parsed
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        # Then: The mood should be the emoji with correct UTF-8 encoding
        mood = post["properties"]["mood"]
        self.assertEqual(mood, "🙌🏻")

        # Then: Verify the bytes are correct UTF-8, not double-encoded
        # Correct UTF-8: f0 9f 99 8c f0 9f 8f bb (🙌🏻)
        # Double-encoded would be: c3 b0 c2 9f c2 99 c2 8c c3 b0 c2 9f c2 8f c2 bb
        mood_bytes = mood.encode("utf-8")
        self.assertEqual(mood_bytes.hex(), "f09f998cf09f8fbb")

    def test_parse_various_emojis_utf8(self):
        """Test parsing various emojis to ensure UTF-8 encoding is preserved."""
        # Given: An org social content with multiple different emojis
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-01-01T10:00:00+0100
:MOOD: 😃
:END:

Happy post!

**
:PROPERTIES:
:ID: 2025-01-01T10:01:00+0100
:MOOD: 🚀
:END:

Launch post!

**
:PROPERTIES:
:ID: 2025-01-01T10:02:00+0100
:MOOD: 💗
:END:

Love post!

**
:PROPERTIES:
:ID: 2025-01-01T10:03:00+0100
:MOOD: 🎉
:END:

Party post!
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: All emojis should be correctly parsed
        self.assertEqual(len(result["posts"]), 4)

        # Then: Verify each emoji and its UTF-8 bytes
        expected_emojis = [
            ("😃", "f09f9883"),
            ("🚀", "f09f9a80"),
            ("💗", "f09f9297"),
            ("🎉", "f09f8e89"),
        ]

        for i, (expected_emoji, expected_bytes) in enumerate(expected_emojis):
            post = result["posts"][i]
            mood = post["properties"]["mood"]
            self.assertEqual(mood, expected_emoji)
            self.assertEqual(mood.encode("utf-8").hex(), expected_bytes)

    @patch("app.feeds.parser.requests.get")
    def test_parse_feed_with_missing_charset_header(self, mock_get):
        """Test parsing a feed when server doesn't specify charset in Content-Type.

        This test validates that the parser correctly handles UTF-8 content
        even when the server doesn't specify charset in the Content-Type header,
        which would cause requests library to default to ISO-8859-1 encoding.
        """
        # Given: A feed content with emoji that would be double-encoded if using response.text
        content_with_emoji = """#+TITLE: Test
#+NICK: test_user

* Posts
**
:PROPERTIES:
:ID: 2025-11-13T12:05:35+0100
:MOOD: 🙌🏻
:END:

Great work!
"""

        # Given: Mock response that simulates server without charset in Content-Type
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.encoding = "ISO-8859-1"  # requests default when no charset
        mock_response.content = content_with_emoji.encode("utf-8")  # Raw UTF-8 bytes
        mock_response.url = "https://example.com/social.org"  # No redirect
        mock_response.history = []  # No redirect history
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # When: We parse the feed from URL
        from app.feeds.parser import parse_org_social

        result = parse_org_social("https://example.com/social.org")

        # Then: The emoji should be correctly parsed (not double-encoded)
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]

        mood = post["properties"]["mood"]
        self.assertEqual(mood, "🙌🏻")

        # Then: Verify the bytes are correct UTF-8, not double-encoded
        mood_bytes = mood.encode("utf-8")
        self.assertEqual(mood_bytes.hex(), "f09f998cf09f8fbb")

        # Then: Verify we're using response.content, not response.text
        # This is critical to avoid double-encoding
        mock_get.assert_called_once_with("https://example.com/social.org", timeout=5)

    def test_parse_v16_metadata_fields(self):
        """Test parsing v1.6 metadata fields (LOCATION, BIRTHDAY, LANGUAGE, PINNED)."""
        # Given: An org social content with v1.6 metadata fields
        content = """#+TITLE: Test User Profile
#+NICK: test_user
#+DESCRIPTION: Test description
#+AVATAR: https://example.com/avatar.jpg
#+LOCATION: Valencia, Spain
#+BIRTHDAY: 1990-05-15
#+LANGUAGE: en es ca
#+PINNED: 2025-01-15T10:00:00+0100

* Posts
** 2025-01-15T10:00:00+0100
:PROPERTIES:
:END:

This is my pinned post.

** 2025-01-16T12:00:00+0100
:PROPERTIES:
:END:

This is a regular post.
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: All v1.6 metadata fields should be correctly parsed
        self.assertEqual(result["metadata"]["location"], "Valencia, Spain")
        self.assertEqual(result["metadata"]["birthday"], "1990-05-15")
        self.assertEqual(result["metadata"]["language"], "en es ca")
        self.assertEqual(result["metadata"]["pinned"], "2025-01-15T10:00:00+0100")

        # Then: Posts should be parsed correctly
        self.assertEqual(len(result["posts"]), 2)

    def test_parse_post_id_in_header(self):
        """Test parsing post ID from header (v1.6 feature)."""
        # Given: An org social content with post ID in header
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
** 2025-01-15T10:00:00+0100
:PROPERTIES:
:LANG: en
:END:

This post has ID in the header.

**
:PROPERTIES:
:ID: 2025-01-16T12:00:00+0100
:END:

This post has ID in properties.
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: Both posts should have correct IDs
        self.assertEqual(len(result["posts"]), 2)

        # Then: First post should have ID from header
        post1 = result["posts"][0]
        self.assertEqual(post1["id"], "2025-01-15T10:00:00+0100")

        # Then: Second post should have ID from properties
        post2 = result["posts"][1]
        self.assertEqual(post2["id"], "2025-01-16T12:00:00+0100")

    def test_parse_post_id_priority_header_over_property(self):
        """Test that header ID takes priority over property ID (v1.6 spec)."""
        # Given: An org social content with post ID in both header and properties
        content = """#+TITLE: Test
#+NICK: test_user

* Posts
** 2025-01-15T10:00:00+0100
:PROPERTIES:
:ID: 2025-01-16T12:00:00+0100
:END:

This post has ID in both places. Header should take priority.
"""

        # When: We parse the content
        from app.feeds.parser import parse_org_social_content

        result = parse_org_social_content(content)

        # Then: Post should have ID from header (priority)
        self.assertEqual(len(result["posts"]), 1)
        post = result["posts"][0]
        self.assertEqual(post["id"], "2025-01-15T10:00:00+0100")

    @patch("app.feeds.parser.requests.get")
    def test_parse_feed_with_301_redirect(self, mock_get):
        """Test that feed redirects (301) are properly detected and handled."""
        # Given: A feed URL that redirects to a new URL
        old_url = "https://old.example.com/social.org"
        new_url = "https://new.example.com/social.org"

        content = """#+TITLE: Test User
#+NICK: test_user

* Posts
** 2025-01-15T10:00:00+0100
:PROPERTIES:
:END:

Test post
"""

        # Given: Mock response with redirect history
        mock_redirect = Mock()
        mock_redirect.status_code = 301

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = content.encode("utf-8")
        mock_response.url = new_url  # Final URL after redirect
        mock_response.history = [mock_redirect]  # Redirect happened
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # When: We parse the feed from old URL
        from app.feeds.parser import parse_org_social

        result = parse_org_social(old_url)

        # Then: The content should be parsed correctly
        self.assertEqual(result["metadata"]["nick"], "test_user")
        self.assertEqual(len(result["posts"]), 1)

    @patch("app.feeds.parser.requests.get")
    def test_validate_feed_with_301_redirect(self, mock_get):
        """Test that feed validation handles redirects properly."""
        # Given: A feed URL that redirects to a new URL
        old_url = "https://old.example.com/social.org"
        new_url = "https://new.example.com/social.org"

        content = """#+TITLE: Test User
#+NICK: test_user

* Posts
"""

        # Given: Mock response with redirect history
        mock_redirect = Mock()
        mock_redirect.status_code = 301

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = content.encode("utf-8")
        mock_response.url = new_url  # Final URL after redirect
        mock_response.history = [mock_redirect]  # Redirect happened
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # When: We validate the feed
        from app.feeds.parser import validate_org_social_feed

        is_valid, error_message = validate_org_social_feed(old_url)

        # Then: The feed should be valid
        self.assertTrue(is_valid)
        self.assertEqual(error_message, "")


class FeedRedirectHandlerTest(TestCase):
    """Test cases for feed redirect handling logic."""

    def test_handle_redirect_updates_feed_url_when_only_old_exists(self):
        """Test updating feed URL when only old feed exists."""
        # Given: A feed exists with old URL
        from app.feeds.models import Feed, Profile
        from app.feeds.parser import _handle_feed_redirect

        old_url = "https://old.example.com/social.org"
        new_url = "https://new.example.com/social.org"

        Feed.objects.create(url=old_url)
        Profile.objects.create(
            feed=old_url, nick="testuser", title="Test User", version="v1"
        )

        # When: Redirect is handled
        _handle_feed_redirect(old_url, new_url)

        # Then: Feed URL should be updated
        self.assertFalse(Feed.objects.filter(url=old_url).exists())
        self.assertTrue(Feed.objects.filter(url=new_url).exists())

        # Then: Profile should point to new URL
        profile = Profile.objects.get(feed=new_url)
        self.assertEqual(profile.nick, "testuser")

    def test_handle_redirect_merges_feeds_when_both_exist(self):
        """Test merging feeds when both old and new URLs exist."""
        # Given: Both old and new feeds exist
        from app.feeds.models import Feed, Profile, Post
        from app.feeds.parser import _handle_feed_redirect
        from django.utils import timezone

        old_url = "https://old.example.com/social.org"
        new_url = "https://new.example.com/social.org"

        # Create old feed and profile
        Feed.objects.create(url=old_url)
        old_profile = Profile.objects.create(
            feed=old_url, nick="olduser", title="Old User", version="v1"
        )
        Post.objects.create(
            profile=old_profile,
            post_id="2025-01-15T10:00:00+0100",
            content="Old post",
            created_at=timezone.now(),
        )

        # Create new feed and profile
        Feed.objects.create(url=new_url)
        new_profile = Profile.objects.create(
            feed=new_url, nick="newuser", title="New User", version="v2"
        )

        # When: Redirect is handled
        _handle_feed_redirect(old_url, new_url)

        # Then: Old feed should be deleted
        self.assertFalse(Feed.objects.filter(url=old_url).exists())
        self.assertTrue(Feed.objects.filter(url=new_url).exists())

        # Then: Old profile should be deleted
        self.assertFalse(Profile.objects.filter(feed=old_url).exists())

        # Then: Post should be migrated to new profile
        post = Post.objects.get(post_id="2025-01-15T10:00:00+0100")
        self.assertEqual(post.profile, new_profile)

    def test_handle_redirect_merges_mentions_without_duplicates(self):
        """Test that mentions are merged correctly, avoiding UNIQUE constraint errors."""
        # Given: Both old and new profiles exist with mentions
        from app.feeds.models import Feed, Profile, Post, Mention
        from app.feeds.parser import _handle_feed_redirect
        from django.utils import timezone

        old_url = "https://old.example.com/social.org"
        new_url = "https://new.example.com/social.org"

        # Create old feed and profile
        Feed.objects.create(url=old_url)
        old_profile = Profile.objects.create(
            feed=old_url, nick="olduser", title="Old User", version="v1"
        )

        # Create new feed and profile
        Feed.objects.create(url=new_url)
        new_profile = Profile.objects.create(
            feed=new_url, nick="newuser", title="New User", version="v2"
        )

        # Create a third profile that mentions both old and new profiles
        third_profile = Profile.objects.create(
            feed="https://third.example.com/social.org",
            nick="third",
            title="Third User",
            version="v1",
        )
        post = Post.objects.create(
            profile=third_profile,
            post_id="2025-01-15T10:00:00+0100",
            content="Mentioning both profiles",
            created_at=timezone.now(),
        )

        # Create mentions: one to old_profile, one to new_profile
        Mention.objects.create(post=post, mentioned_profile=old_profile, nickname="old")
        Mention.objects.create(post=post, mentioned_profile=new_profile, nickname="new")

        # When: Redirect is handled (this should NOT raise UNIQUE constraint error)
        _handle_feed_redirect(old_url, new_url)

        # Then: Old profile should be deleted
        self.assertFalse(Profile.objects.filter(feed=old_url).exists())

        # Then: Only one mention should remain (the duplicate was deleted)
        mentions = Mention.objects.filter(post=post)
        self.assertEqual(mentions.count(), 1)
        self.assertEqual(mentions.first().mentioned_profile, new_profile)
