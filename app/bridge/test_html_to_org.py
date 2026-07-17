from django.test import SimpleTestCase

from app.bridge.html_to_org import escape_org_lines, html_to_org, html_to_text


class HtmlToOrgTest(SimpleTestCase):
    """Test cases for the HTML to Org converter."""

    def test_paragraphs_become_blank_line_separated(self):
        # Given: HTML with two paragraphs
        html = "<p>First paragraph</p><p>Second paragraph</p>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: Paragraphs are separated by a blank line
        self.assertEqual(result, "First paragraph\n\nSecond paragraph")

    def test_br_becomes_newline(self):
        # Given: HTML with a line break inside a paragraph
        html = "<p>First line<br>Second line</p>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: The break is kept as a single newline
        self.assertEqual(result, "First line\nSecond line")

    def test_link_with_text_becomes_org_link(self):
        # Given: An anchor with its own text
        html = '<p>Read <a href="https://example.com/post">this article</a></p>'

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: An Org link with description is produced
        self.assertEqual(result, "Read [[https://example.com/post][this article]]")

    def test_link_with_url_as_text_becomes_plain_org_link(self):
        # Given: An anchor whose text is the URL itself
        html = '<a href="https://example.com">https://example.com</a>'

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: A plain Org link is produced
        self.assertEqual(result, "[[https://example.com]]")

    def test_hashtag_and_mention_links_stay_as_plain_text(self):
        # Given: Mastodon-style hashtag and mention anchors
        html = (
            '<p>Hi <a href="https://m.example/@bob" class="u-url mention">'
            "@bob</a> about "
            '<a href="https://m.example/tags/emacs" class="mention hashtag">'
            "#emacs</a></p>"
        )

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: No Org links are produced, only their text
        self.assertEqual(result, "Hi @bob about #emacs")

    def test_emphasis_tags_become_org_markers(self):
        # Given: HTML with bold, italic and code
        html = "<p><strong>bold</strong> <em>italic</em> <code>code</code></p>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: Org emphasis markers are used
        self.assertEqual(result, "*bold* /italic/ ~code~")

    def test_list_items_become_org_list(self):
        # Given: An unordered list
        html = "<ul><li>One</li><li>Two</li></ul>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: Each item becomes a dash line
        self.assertEqual(result, "- One\n- Two")

    def test_blockquote_becomes_quote_block(self):
        # Given: A quoted paragraph
        html = "<blockquote><p>Wise words</p></blockquote>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: The text is wrapped in a quote block
        self.assertEqual(result, "#+BEGIN_QUOTE\n\nWise words\n\n#+END_QUOTE")

    def test_pre_becomes_example_block(self):
        # Given: Preformatted content
        html = "<pre>print('hi')</pre>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: The content is wrapped in an example block preserving text
        self.assertEqual(result, "#+BEGIN_EXAMPLE\nprint('hi')\n#+END_EXAMPLE")

    def test_invisible_spans_are_skipped(self):
        # Given: A Mastodon-style shortened URL anchor
        html = (
            '<a href="https://example.com/very/long/path">'
            '<span class="invisible">https://</span>'
            '<span class="ellipsis">example.com/very</span></a>'
        )

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: The invisible prefix is not part of the link text
        self.assertEqual(
            result, "[[https://example.com/very/long/path][example.com/very]]"
        )

    def test_image_becomes_org_link_with_alt_text(self):
        # Given: An image with alt text and another without it
        html = (
            '<p><img src="https://example.com/a.png" alt="A comic"/></p>'
            '<p><img src="https://example.com/b.png"/></p>'
        )

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: Images become Org links, using alt as description
        self.assertEqual(
            result,
            "[[https://example.com/a.png][A comic]]\n\n[[https://example.com/b.png]]",
        )

    def test_image_wrapped_in_anchor_keeps_only_the_image_link(self):
        # Given: An image wrapped in an anchor (common in RSS feeds)
        html = (
            '<a href="https://example.com/post">'
            '<img src="https://example.com/a.png" alt="A comic"/></a>'
        )

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: No nested Org links are produced
        self.assertEqual(result, "[[https://example.com/a.png][A comic]]")

    def test_html_entities_are_decoded(self):
        # Given: HTML with entities
        html = "<p>Fish &amp; chips &lt;3</p>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: Entities are decoded
        self.assertEqual(result, "Fish & chips <3")

    def test_headline_injection_is_escaped(self):
        # Given: Remote content that looks like Org Social headlines
        html = "<p>** 2025-01-01T00:00:00+00:00<br>* Posts</p>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: The lines are prefixed so they cannot break the feed
        for line in result.split("\n"):
            self.assertFalse(line.startswith("*"))

    def test_empty_and_missing_html_return_empty_string(self):
        # Given: Empty and missing input
        # When: They are converted
        # Then: The result is an empty string
        self.assertEqual(html_to_org(""), "")
        self.assertEqual(html_to_org(None), "")

    def test_unknown_tags_are_stripped_keeping_text(self):
        # Given: HTML with tags the converter does not know
        html = "<article><section>Some text</section></article>"

        # When: It is converted to Org
        result = html_to_org(html)

        # Then: The text survives without the tags
        self.assertEqual(result, "Some text")


class HtmlToTextTest(SimpleTestCase):
    """Test cases for the single-line text converter."""

    def test_multiline_html_becomes_single_line(self):
        # Given: HTML with several paragraphs
        html = "<p>Bio line one</p><p>Bio line two</p>"

        # When: It is converted to plain text
        result = html_to_text(html)

        # Then: Everything is collapsed into one line
        self.assertEqual(result, "Bio line one Bio line two")


class EscapeOrgLinesTest(SimpleTestCase):
    """Test cases for headline escaping."""

    def test_one_and_two_asterisk_headlines_are_escaped(self):
        # Given: Text with dangerous headline-like lines
        text = "* Posts\n** 2025-01-01T00:00:00+00:00\nnormal"

        # When: It is escaped
        result = escape_org_lines(text)

        # Then: Dangerous lines are prefixed with a space
        self.assertEqual(result, " * Posts\n ** 2025-01-01T00:00:00+00:00\nnormal")

    def test_post_titles_with_three_asterisks_are_kept(self):
        # Given: A legal Org Social post title line
        text = "*** My title"

        # When: It is escaped
        result = escape_org_lines(text)

        # Then: The title line is untouched
        self.assertEqual(result, "*** My title")

    def test_bold_text_at_line_start_is_kept(self):
        # Given: A line starting with Org bold (no space after asterisk)
        text = "*bold* rest"

        # When: It is escaped
        result = escape_org_lines(text)

        # Then: The line is untouched
        self.assertEqual(result, "*bold* rest")

    def test_escaping_is_idempotent(self):
        # Given: Already escaped text
        text = escape_org_lines("** 2025-01-01T00:00:00+00:00")

        # When: It is escaped again
        result = escape_org_lines(text)

        # Then: Nothing changes
        self.assertEqual(result, text)
