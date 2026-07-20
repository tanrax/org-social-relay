from urllib.parse import quote, urlparse

from django.conf import settings
from django.db import models

# Path fragments that identify a bridge virtual feed, on this relay or any other
BRIDGE_PATH_MARKERS = ("/bridge/activitypub/", "/bridge/rss/")


def is_bridge_feed_url(url):
    """
    True when the URL points to a bridge virtual feed.

    Bridges help users connect to external content but are not real
    Org Social accounts, so they must stay out of the feed registry
    and the statistics.
    """
    path = urlparse(url).path
    return any(marker in path for marker in BRIDGE_PATH_MARKERS)


def bridge_urls_q(field):
    """
    Q object matching rows whose `field` URL belongs to a bridge virtual
    feed. Use with exclude() to leave bridges out of listings and stats.
    """
    q = models.Q()
    for marker in BRIDGE_PATH_MARKERS:
        q |= models.Q(**{f"{field}__contains": marker})
    return q


def bridge_base_url():
    """
    Base URL of this relay, used to build the public URL of virtual feeds.
    """
    domain = settings.SITE_DOMAIN
    scheme = "http" if domain.startswith(("localhost", "127.")) else "https"
    return f"{scheme}://{domain}"


def activitypub_feed_url(handle):
    """Public URL of the virtual feed of a bridged ActivityPub account."""
    return f"{bridge_base_url()}/bridge/activitypub/@{handle}/"


def rss_feed_url(source_url):
    """Public URL of the virtual feed of a bridged RSS feed."""
    return f"{bridge_base_url()}/bridge/rss/?url={quote(source_url, safe='')}"


class BridgedActivityPubAccount(models.Model):
    """
    An ActivityPub account (e.g. a Mastodon user) exposed as a virtual
    Org Social feed at /bridge/activitypub/@{handle}/.
    """

    handle = models.CharField(
        max_length=255,
        unique=True,
        help_text="Normalized handle in user@instance form (lowercase)",
    )
    actor_url = models.URLField(
        max_length=500, help_text="ActivityPub actor document URL"
    )
    outbox_url = models.URLField(
        max_length=500, blank=True, help_text="ActivityPub outbox URL"
    )
    profile = models.OneToOneField(
        "feeds.Profile",
        on_delete=models.CASCADE,
        related_name="activitypub_bridge",
        help_text="Profile that stores the bridged data",
    )
    last_refreshed_at = models.DateTimeField(
        null=True, blank=True, help_text="Last successful fetch from the origin"
    )
    last_accessed_at = models.DateTimeField(
        help_text="Last time a client requested this virtual feed"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["handle"]

    def __str__(self):
        return f"@{self.handle}"

    @property
    def feed_url(self):
        return activitypub_feed_url(self.handle)


class BridgedRssFeed(models.Model):
    """
    An RSS/Atom feed exposed as a virtual Org Social feed at
    /bridge/rss/?url={source_url}.
    """

    source_url = models.URLField(
        max_length=500, unique=True, help_text="URL of the RSS/Atom feed"
    )
    profile = models.OneToOneField(
        "feeds.Profile",
        on_delete=models.CASCADE,
        related_name="rss_bridge",
        help_text="Profile that stores the bridged data",
    )
    last_refreshed_at = models.DateTimeField(
        null=True, blank=True, help_text="Last successful fetch from the origin"
    )
    last_accessed_at = models.DateTimeField(
        help_text="Last time a client requested this virtual feed"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["source_url"]

    def __str__(self):
        return self.source_url

    @property
    def feed_url(self):
        return rss_feed_url(self.source_url)
