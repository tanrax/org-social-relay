import os
import tempfile
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
