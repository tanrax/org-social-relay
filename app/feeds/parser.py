import re
import requests
from typing import Dict, Any


def parse_org_social(url: str) -> Dict[str, Any]:
    """
    Parse an Org Social file from a URL and return structured data.

    Args:
        url: The URL to the social.org file

    Returns:
        Dictionary containing parsed metadata and posts
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.text
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch URL {url}: {str(e)}")

    # Initialize result structure
    result: Dict[str, Any] = {
        "metadata": {
            "title": "",
            "nick": "",
            "description": "",
            "avatar": "",
            "links": [],
            "follows": [],
            "contacts": [],
        },
        "posts": [],
    }

    # Parse metadata with regex
    title_match = re.search(r"^\s*\#\+TITLE:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["title"] = title_match.group(1).strip() if title_match else ""

    nick_match = re.search(r"^\s*\#\+NICK:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["nick"] = nick_match.group(1).strip() if nick_match else ""

    description_match = re.search(
        r"^\s*\#\+DESCRIPTION:\s*(.+)$", content, re.MULTILINE
    )
    result["metadata"]["description"] = (
        description_match.group(1).strip() if description_match else ""
    )

    avatar_match = re.search(r"^\s*\#\+AVATAR:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["avatar"] = avatar_match.group(1).strip() if avatar_match else ""

    # Parse multiple values
    result["metadata"]["links"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+LINK:\s*(.+)$", content, re.MULTILINE)
    ]
    result["metadata"]["contacts"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+CONTACT:\s*(.+)$", content, re.MULTILINE)
    ]

    # Parse follows (can have nickname)
    follow_matches = re.finditer(r"^\s*\#\+FOLLOW:\s*(.+)$", content, re.MULTILINE)
    for match in follow_matches:
        follow_data = match.group(1).strip()
        parts = follow_data.split()
        if len(parts) == 1:
            result["metadata"]["follows"].append({"url": parts[0], "nickname": ""})
        elif len(parts) >= 2:
            result["metadata"]["follows"].append(
                {"nickname": parts[0], "url": parts[1]}
            )

    # Parse posts - find everything after * Posts
    posts_pattern = r"\*\s+Posts\s*\n(.*)"
    posts_match = re.search(posts_pattern, content, re.DOTALL)
    if posts_match:
        posts_content = posts_match.group(1)

        # Split posts by ** headers
        post_pattern = r"\*\*\s*\n(?::PROPERTIES:\s*\n((?::[^:\n]+:[^\n]*\n)*):END:\s*\n)?(.*?)(?=\n\*\*|\Z)"
        post_matches = re.finditer(
            post_pattern, posts_content, re.DOTALL | re.MULTILINE
        )

        for post_match in post_matches:
            properties_text = post_match.group(1) or ""
            content_text = post_match.group(2).strip() if post_match.group(2) else ""

            post: Dict[str, Any] = {
                "id": "",
                "content": content_text,
                "properties": {},
                "mentions": [],
                "poll_options": [],
            }

            # Parse properties
            if properties_text:
                prop_matches = re.finditer(r":([^:]+):\s*([^\n]*)", properties_text)
                for prop_match in prop_matches:
                    prop_name = prop_match.group(1).lower().strip()
                    prop_value = prop_match.group(2).strip()
                    post["properties"][prop_name] = prop_value
                    if prop_name == "id":
                        post["id"] = prop_value

            # Extract mentions from content
            mention_matches = re.finditer(
                r"\[\[org-social:([^\]]+)\]\[([^\]]+)\]\]", content_text
            )
            post["mentions"] = [
                {"url": m.group(1), "nickname": m.group(2)} for m in mention_matches
            ]

            # Extract poll options from content
            poll_matches = re.finditer(
                r"^\s*-\s*\[\s*\]\s*(.+)$", content_text, re.MULTILINE
            )
            post["poll_options"] = [m.group(1).strip() for m in poll_matches]

            if post["id"]:  # Only add posts with valid ID
                result["posts"].append(post)

    return result


def parse_org_social_content(content: str) -> Dict[str, Any]:
    """
    Parse Org Social content directly and return structured data.

    Args:
        content: The raw content of the social.org file

    Returns:
        Dictionary containing parsed metadata and posts
    """
    # Initialize result structure
    result: Dict[str, Any] = {
        "metadata": {
            "title": "",
            "nick": "",
            "description": "",
            "avatar": "",
            "links": [],
            "follows": [],
            "contacts": [],
        },
        "posts": [],
    }

    # Parse metadata with regex
    title_match = re.search(r"^\s*\#\+TITLE:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["title"] = title_match.group(1).strip() if title_match else ""

    nick_match = re.search(r"^\s*\#\+NICK:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["nick"] = nick_match.group(1).strip() if nick_match else ""

    description_match = re.search(
        r"^\s*\#\+DESCRIPTION:\s*(.+)$", content, re.MULTILINE
    )
    result["metadata"]["description"] = (
        description_match.group(1).strip() if description_match else ""
    )

    avatar_match = re.search(r"^\s*\#\+AVATAR:\s*(.+)$", content, re.MULTILINE)
    result["metadata"]["avatar"] = avatar_match.group(1).strip() if avatar_match else ""

    # Parse multiple values
    result["metadata"]["links"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+LINK:\s*(.+)$", content, re.MULTILINE)
    ]
    result["metadata"]["contacts"] = [
        match.group(1).strip()
        for match in re.finditer(r"^\s*\#\+CONTACT:\s*(.+)$", content, re.MULTILINE)
    ]

    # Parse follows (can have nickname)
    follow_matches = re.finditer(r"^\s*\#\+FOLLOW:\s*(.+)$", content, re.MULTILINE)
    for match in follow_matches:
        follow_data = match.group(1).strip()
        parts = follow_data.split()
        if len(parts) == 1:
            result["metadata"]["follows"].append({"url": parts[0], "nickname": ""})
        elif len(parts) >= 2:
            result["metadata"]["follows"].append(
                {"nickname": parts[0], "url": parts[1]}
            )

    # Parse posts - find everything after * Posts
    posts_pattern = r"\*\s+Posts\s*\n(.*)"
    posts_match = re.search(posts_pattern, content, re.DOTALL)
    if posts_match:
        posts_content = posts_match.group(1)

        # Split posts by ** headers
        post_pattern = r"\*\*\s*\n(?::PROPERTIES:\s*\n((?::[^:\n]+:[^\n]*\n)*):END:\s*\n)?(.*?)(?=\n\*\*|\Z)"
        post_matches = re.finditer(
            post_pattern, posts_content, re.DOTALL | re.MULTILINE
        )

        for post_match in post_matches:
            properties_text = post_match.group(1) or ""
            content_text = post_match.group(2).strip() if post_match.group(2) else ""

            post: Dict[str, Any] = {
                "id": "",
                "content": content_text,
                "properties": {},
                "mentions": [],
                "poll_options": [],
            }

            # Parse properties
            if properties_text:
                prop_matches = re.finditer(r":([^:]+):\s*([^\n]*)", properties_text)
                for prop_match in prop_matches:
                    prop_name = prop_match.group(1).lower().strip()
                    prop_value = prop_match.group(2).strip()
                    post["properties"][prop_name] = prop_value
                    if prop_name == "id":
                        post["id"] = prop_value

            # Extract mentions from content
            mention_matches = re.finditer(
                r"\[\[org-social:([^\]]+)\]\[([^\]]+)\]\]", content_text
            )
            post["mentions"] = [
                {"url": m.group(1), "nickname": m.group(2)} for m in mention_matches
            ]

            # Extract poll options from content
            poll_matches = re.finditer(
                r"^\s*-\s*\[\s*\]\s*(.+)$", content_text, re.MULTILINE
            )
            post["poll_options"] = [m.group(1).strip() for m in poll_matches]

            if post["id"]:  # Only add posts with valid ID
                result["posts"].append(post)

    return result
