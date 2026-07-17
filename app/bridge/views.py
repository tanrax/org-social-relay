"""
Bridge endpoints: expose ActivityPub accounts and RSS/Atom feeds as
virtual social.org files that any Org Social client can #+FOLLOW:.

Registration is implicit: the first GET of an unknown account fetches
it from the origin and stores it. Later requests are served from the
database; the periodic refresh task keeps active bridges up to date,
and a request older than REFRESH_ON_ACCESS triggers an inline refresh.
"""

import logging
from datetime import timedelta

from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import store
from .activitypub import normalize_handle
from .fetching import BridgeError
from .models import BridgedActivityPubAccount, BridgedRssFeed
from .org_renderer import render_profile_org

logger = logging.getLogger(__name__)

# A GET on data older than this triggers a synchronous refresh, which
# also reactivates bridges that fell out of the periodic refresh window
REFRESH_ON_ACCESS = timedelta(hours=24)
# last_accessed_at is written at most once per hour
ACCESS_UPDATE_THROTTLE = timedelta(hours=1)

MAX_SOURCE_URL_LENGTH = 500


def _error_response(errors, http_status):
    return Response(
        {"type": "Error", "errors": errors, "data": None}, status=http_status
    )


def _serve_bridge(bridge, refresh_callable):
    """Common flow: refresh if stale, track access, render the org file."""
    now = timezone.now()

    if (
        bridge.last_refreshed_at is None
        or now - bridge.last_refreshed_at > REFRESH_ON_ACCESS
    ):
        try:
            refresh_callable(bridge)
        except BridgeError as e:
            # Serve the stored copy; the origin may recover later
            logger.warning(f"Inline refresh failed for {bridge}: {e}")

    if now - bridge.last_accessed_at > ACCESS_UPDATE_THROTTLE:
        bridge.last_accessed_at = now
        bridge.save(update_fields=["last_accessed_at"])

    posts = bridge.profile.posts.order_by("created_at")
    content = render_profile_org(bridge.profile, posts)
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


class BridgeIndexView(APIView):
    """Information about the available bridges."""

    def get(self, request):
        return Response(
            {
                "type": "Success",
                "errors": [],
                "data": {
                    "description": (
                        "Bridges expose external accounts as virtual "
                        "social.org feeds that can be followed with #+FOLLOW:"
                    ),
                },
                "_links": {
                    "self": {"href": "/bridge/", "method": "GET"},
                    "activitypub-feed": {
                        "href": "/bridge/activitypub/@{user}@{instance}/",
                        "method": "GET",
                        "templated": True,
                    },
                    "activitypub-list": {
                        "href": "/bridge/activitypub/",
                        "method": "GET",
                    },
                    "rss-feed": {
                        "href": "/bridge/rss/?url={feed_url}",
                        "method": "GET",
                        "templated": True,
                    },
                    "rss-list": {"href": "/bridge/rss/", "method": "GET"},
                },
            }
        )


class ActivityPubBridgeListView(APIView):
    """List bridged ActivityPub accounts."""

    def get(self, request):
        data = [
            {"handle": f"@{bridge.handle}", "feed": bridge.feed_url}
            for bridge in BridgedActivityPubAccount.objects.all()
        ]
        return Response(
            {
                "type": "Success",
                "errors": [],
                "data": data,
                "_links": {
                    "self": {"href": "/bridge/activitypub/", "method": "GET"},
                },
            }
        )


class ActivityPubBridgeFeedView(APIView):
    """Serve an ActivityPub account as a virtual social.org file."""

    def get(self, request, handle):
        normalized = normalize_handle(handle)
        if normalized is None:
            return _error_response(
                ["Invalid handle. Expected format: @user@instance"],
                status.HTTP_400_BAD_REQUEST,
            )

        # Redirect non-canonical spellings so each account has one URL
        if handle != f"@{normalized}":
            return HttpResponsePermanentRedirect(f"/bridge/activitypub/@{normalized}/")

        bridge = (
            BridgedActivityPubAccount.objects.select_related("profile")
            .filter(handle=normalized)
            .first()
        )

        if bridge is None:
            try:
                bridge = store.create_activitypub_bridge(normalized)
            except BridgeError as e:
                logger.warning(f"Could not bridge @{normalized}: {e}")
                return _error_response(
                    [f"Could not fetch ActivityPub account: {e}"],
                    status.HTTP_502_BAD_GATEWAY,
                )

        return _serve_bridge(bridge, store.refresh_activitypub_bridge)


class RssBridgeView(APIView):
    """
    With ?url= serves an RSS/Atom feed as a virtual social.org file;
    without it, lists the bridged RSS feeds.
    """

    def get(self, request):
        source_url = request.query_params.get("url")

        if source_url is None:
            data = [
                {"url": bridge.source_url, "feed": bridge.feed_url}
                for bridge in BridgedRssFeed.objects.all()
            ]
            return Response(
                {
                    "type": "Success",
                    "errors": [],
                    "data": data,
                    "_links": {
                        "self": {"href": "/bridge/rss/", "method": "GET"},
                    },
                }
            )

        source_url = source_url.strip()
        if (
            not source_url.startswith(("http://", "https://"))
            or len(source_url) > MAX_SOURCE_URL_LENGTH
        ):
            return _error_response(
                ["Invalid url parameter. Expected an http(s) feed URL"],
                status.HTTP_400_BAD_REQUEST,
            )

        bridge = (
            BridgedRssFeed.objects.select_related("profile")
            .filter(source_url=source_url)
            .first()
        )

        if bridge is None:
            try:
                bridge = store.create_rss_bridge(source_url)
            except BridgeError as e:
                logger.warning(f"Could not bridge RSS feed {source_url}: {e}")
                return _error_response(
                    [f"Could not fetch RSS feed: {e}"],
                    status.HTTP_502_BAD_GATEWAY,
                )

        return _serve_bridge(bridge, store.refresh_rss_bridge)
