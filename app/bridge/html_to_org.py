"""
Minimal HTML to Org Mode text converter for bridged content.

Converts the HTML bodies published by ActivityPub servers and RSS feeds
into Org text suitable for a post body inside a virtual social.org file.
Only the common subset is handled (paragraphs, line breaks, links,
emphasis, lists, quotes and preformatted blocks); unknown tags are
stripped, keeping their text.
"""

import re
from html.parser import HTMLParser

# A post body line must never look like an Org Social headline (* or **
# followed by whitespace) because it would break the virtual feed
# structure. Three or more asterisks are legal (post titles).
_HEADLINE_RE = re.compile(r"^(\*{1,2})(\s|$)")

_EMPHASIS_TAGS = {
    "strong": "*",
    "b": "*",
    "em": "/",
    "i": "/",
    "code": "~",
    "tt": "~",
}

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def escape_org_lines(text):
    """
    Prefix a space to any line that would be parsed as an Org Social
    headline, so remote content cannot inject fake posts.
    """
    lines = []
    for line in text.split("\n"):
        if _HEADLINE_RE.match(line):
            line = " " + line
        lines.append(line)
    return "\n".join(lines)


class _OrgHTMLConverter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.parts = []
        self.anchor_stack = []  # (href, render_as_plain_text, position)
        self.emphasis_stack = []  # (marker, position)
        self.in_list_item = False
        self.pre_depth = 0
        self.pre_parts = []
        self.invisible_depth = 0

    # --- block helpers -------------------------------------------------

    def _flush(self):
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text).strip()
        self.parts = []
        if not text:
            return
        if self.in_list_item:
            self.blocks.append(f"- {text}")
        else:
            self.blocks.append(text)

    def _append_block(self, block):
        self._flush()
        self.blocks.append(block)

    # --- parser events -------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if self.pre_depth:
            if tag == "pre":
                self.pre_depth += 1
            return

        attrs_dict = dict(attrs)
        css_classes = (attrs_dict.get("class") or "").lower()

        if tag in ("p", "div"):
            self._flush()
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "a":
            href = (attrs_dict.get("href") or "").strip()
            plain = "mention" in css_classes or "hashtag" in css_classes
            self.anchor_stack.append((href, plain, len(self.parts)))
        elif tag in _EMPHASIS_TAGS:
            self.emphasis_stack.append((_EMPHASIS_TAGS[tag], len(self.parts)))
        elif tag in ("ul", "ol"):
            self._flush()
        elif tag == "li":
            self._flush()
            self.in_list_item = True
        elif tag == "blockquote":
            self._append_block("#+BEGIN_QUOTE")
        elif tag == "pre":
            self._flush()
            self.pre_depth = 1
            self.pre_parts = []
        elif tag in _HEADING_TAGS:
            self._flush()
            self.emphasis_stack.append(("*", len(self.parts)))
        elif tag == "img":
            src = (attrs_dict.get("src") or "").strip()
            if src and "]" not in src:
                alt = " ".join((attrs_dict.get("alt") or "").split())
                alt = alt.replace("]", ")")
                if alt:
                    self.parts.append(f"[[{src}][{alt}]]")
                else:
                    self.parts.append(f"[[{src}]]")
        elif tag == "span" and "invisible" in css_classes:
            self.invisible_depth += 1

    def handle_endtag(self, tag):
        if self.pre_depth:
            if tag == "pre":
                self.pre_depth -= 1
                if self.pre_depth == 0:
                    code = "".join(self.pre_parts).strip("\n")
                    self._append_block(f"#+BEGIN_EXAMPLE\n{code}\n#+END_EXAMPLE")
            return

        if tag == "a" and self.anchor_stack:
            href, plain, position = self.anchor_stack.pop()
            text = "".join(self.parts[position:]).strip()
            if plain or not href or "]" in href or "[[" in text:
                # Org links cannot nest: anchors wrapping an image keep
                # only the inner image link
                rendered = text
            elif not text or text == href:
                rendered = f"[[{href}]]"
            else:
                text = text.replace("]", ")")
                rendered = f"[[{href}][{text}]]"
            self.parts[position:] = [rendered]
        elif tag in _EMPHASIS_TAGS and self.emphasis_stack:
            marker, position = self.emphasis_stack.pop()
            text = "".join(self.parts[position:]).strip()
            self.parts[position:] = [f"{marker}{text}{marker}"] if text else []
        elif tag in ("p", "div", "ul", "ol"):
            self._flush()
        elif tag == "li":
            self._flush()
            self.in_list_item = False
        elif tag == "blockquote":
            self._append_block("#+END_QUOTE")
        elif tag in _HEADING_TAGS and self.emphasis_stack:
            marker, position = self.emphasis_stack.pop()
            text = "".join(self.parts[position:]).strip()
            self.parts[position:] = [f"{marker}{text}{marker}"] if text else []
            self._flush()
        elif tag == "span" and self.invisible_depth:
            self.invisible_depth -= 1

    def handle_data(self, data):
        if self.pre_depth:
            self.pre_parts.append(data)
            return
        if self.invisible_depth:
            return
        self.parts.append(data.replace("\n", " "))

    def result(self):
        self._flush()
        # Consecutive list items stay together; everything else is
        # separated by a blank line
        chunks = []
        previous_is_item = False
        for block in self.blocks:
            is_item = block.startswith("- ")
            if chunks and is_item and previous_is_item:
                chunks.append("\n")
            elif chunks:
                chunks.append("\n\n")
            chunks.append(block)
            previous_is_item = is_item
        return "".join(chunks)


def html_to_org(html):
    """
    Convert an HTML fragment to Org text. Returns plain text with Org
    links/emphasis, paragraphs separated by blank lines, and headline
    injection escaped. Never raises on malformed HTML.
    """
    if not html:
        return ""
    converter = _OrgHTMLConverter()
    try:
        converter.feed(html)
        converter.close()
    except Exception:
        # html.parser is very tolerant; this is a last-resort guard
        return escape_org_lines(re.sub(r"<[^>]+>", " ", html).strip())
    return escape_org_lines(converter.result())


def html_to_text(html):
    """Convert an HTML fragment to a single line of plain text."""
    org = html_to_org(html)
    return re.sub(r"\s+", " ", org).strip()
