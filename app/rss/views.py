from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Rss201rev2Feed
from django.core.cache import cache
from django.db.models import Q
from django.conf import settings
from django.utils.xmlutils import SimplerXMLGenerator
import hashlib
import re
import logging

from app.feeds.models import Post

try:
    from orgpython import to_html as org_to_html
    HAS_ORGPYTHON = True
except ImportError:
    HAS_ORGPYTHON = False

logger = logging.getLogger(__name__)


class CustomRss201rev2Feed(Rss201rev2Feed):
    """Custom RSS generator that adds author field properly"""

    def add_item_elements(self, handler, item):
        """Add item elements including author"""
        super().add_item_elements(handler, item)

        # Add author field if provided
        if item.get('author'):
            handler.addQuickElement('author', item['author'])


class LatestPostsFeed(Feed):
    """RSS feed for latest posts from Org Social Relay"""

    feed_type = CustomRss201rev2Feed

    def get_object(self, request):
        """Process query parameters"""
        tag = request.GET.get('tag')
        feed_url = request.GET.get('feed')
        return {'tag': tag, 'feed': feed_url}

    def title(self, obj):
        """Generate feed title based on filters"""
        if obj['tag']:
            return f"Org Social Relay - Posts tagged with '{obj['tag']}'"
        elif obj['feed']:
            return f"Org Social Relay - Posts from {obj['feed']}"
        return "Org Social Relay - Latest Posts"

    def link(self, obj):
        """Generate feed link"""
        site_domain = settings.SITE_DOMAIN
        protocol = 'https' if not settings.DEBUG else 'http'
        base_url = f"{protocol}://{site_domain}/rss.xml"

        if obj['tag']:
            return f"{base_url}?tag={obj['tag']}"
        elif obj['feed']:
            return f"{base_url}?feed={obj['feed']}"
        return base_url

    def description(self, obj):
        """Generate feed description based on filters"""
        if obj['tag']:
            return f"Latest posts from Org Social Relay tagged with '{obj['tag']}'"
        elif obj['feed']:
            return f"Latest posts from {obj['feed']} on Org Social Relay"
        return "Latest posts from all registered feeds on Org Social Relay"

    def items(self, obj):
        """Return items for the feed, limited to 200 posts"""
        # Build cache key based on filters
        cache_parts = ['rss_feed']
        if obj['tag']:
            cache_parts.append(f"tag_{hashlib.md5(obj['tag'].encode()).hexdigest()[:8]}")
        elif obj['feed']:
            cache_parts.append(f"feed_{hashlib.md5(obj['feed'].encode()).hexdigest()[:8]}")
        else:
            cache_parts.append('all')

        cache_key = '_'.join(cache_parts)
        cached_posts = cache.get(cache_key)

        if cached_posts is not None:
            return cached_posts

        # Build query
        posts_query = Post.objects.select_related('profile').order_by('-created_at')

        # Apply filters
        if obj['tag']:
            # Search by specific tag (exact word match, case insensitive)
            tag_escaped = re.escape(obj['tag'])
            tag_pattern = rf"(^|[\s]){tag_escaped}([\s]|$)"
            posts_query = posts_query.filter(tags__iregex=tag_pattern)
        elif obj['feed']:
            # Filter by author feed
            posts_query = posts_query.filter(profile__feed=obj['feed'])

        # Limit to 200 posts as per specification
        posts = list(posts_query[:200])

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, posts, None)

        return posts

    def item_title(self, item):
        """Generate item title"""
        # Use first line as title, or entire content if no line breaks
        content = item.content.strip()
        if '\n' in content:
            # Use first line as title (complete, no limits)
            first_line = content.split('\n')[0].strip()
            return first_line if first_line else 'Untitled post'

        # Use entire content as title (no limits)
        return content if content else 'Untitled post'

    def item_description(self, item):
        """Return full post content as description, converted from Org to HTML"""
        if not item.content:
            return ''

        # Convert Org mode content to HTML if org-python is available
        if HAS_ORGPYTHON:
            try:
                # Convert org-mode to HTML
                # We disable toc as we're showing individual posts
                # highlight=True enables syntax highlighting for code blocks
                html_content = org_to_html(item.content, toc=False, highlight=True)
                return html_content
            except Exception as e:
                logger.warning(f"Failed to convert Org to HTML for post {item.post_id}: {e}")
                # Fallback to plain text
                return item.content

        # If org-python is not available, return plain text
        return item.content

    def item_link(self, item):
        """Generate item link (post URL)"""
        return f"{item.profile.feed}#{item.post_id}"

    def item_author_name(self, item):
        """Return author name"""
        return item.profile.nick

    def item_author_email(self, item):
        """Return author email - using feed URL as identifier"""
        # RSS 2.0 requires email format for author, but we don't have emails
        # We'll return None and handle it differently
        return None

    def item_extra_kwargs(self, item):
        """Add custom author field"""
        return {
            'author': item.profile.nick
        }

    def item_pubdate(self, item):
        """Return publication date"""
        return item.created_at

    def item_categories(self, item):
        """Return post tags as categories"""
        if item.tags:
            return item.tags.split()
        return []

    def item_guid(self, item):
        """Return unique identifier for the item"""
        return f"{item.profile.feed}#{item.post_id}"

    def item_guid_is_permalink(self, item):
        """The GUID is a permalink"""
        return True
