from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
import logging

from app.bridge.models import bridge_urls_q
from app.feeds.models import Feed, Follow, Post, Profile

logger = logging.getLogger(__name__)


class StatsView(APIView):
    """Aggregated statistics grouped by year and month, plus global counters"""

    def get(self, request):
        cache_key = "stats"
        cached_response = cache.get(cache_key)

        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

        response_data = {
            "type": "Success",
            "errors": [],
            "data": {
                "years": self._get_monthly_stats(),
                "global": self._get_global_stats(),
            },
            "meta": {
                "generated_at": timezone.now().isoformat(),
            },
            "_links": {
                "self": {"href": "/stats/", "method": "GET"},
                "feeds": {"href": "/feeds/", "method": "GET"},
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)

    def _get_monthly_stats(self):
        """Aggregate post counters grouped by year and month.

        A post belongs to the month of its ID (RFC 3339 timestamp), which
        is stored parsed in created_at. The four type counters are disjoint
        (posts + replies + reactions + boosts = total_posts), while
        group_messages and polls are transversal.
        """
        is_reply = ~Q(reply_to="")
        # Same criterion as the replies endpoint: a reaction is a reply with
        # a mood and empty or whitespace-only content
        is_reaction = is_reply & ~Q(mood="") & Q(content__regex=r"^\s*$")

        # Bridged posts belong to external authors, not to real accounts
        monthly = (
            Post.objects.exclude(bridge_urls_q("profile__feed"))
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(
                active_accounts=Count("profile", distinct=True),
                total_posts=Count("id"),
                posts=Count("id", filter=Q(reply_to="") & Q(include="")),
                replies=Count("id", filter=is_reply & ~is_reaction),
                boosts=Count("id", filter=Q(reply_to="") & ~Q(include="")),
                reactions=Count("id", filter=is_reaction),
                group_messages=Count("id", filter=~Q(group="")),
                polls=Count("id", filter=Q(poll_end__isnull=False)),
            )
            .order_by("month")
        )

        years = {}
        for row in monthly:
            month = row["month"]
            if month is None:
                continue

            year_key = f"{month.year:04d}"
            month_key = f"{month.month:02d}"
            years.setdefault(year_key, {})[month_key] = {
                "active_accounts": row["active_accounts"],
                "total_posts": row["total_posts"],
                "posts": row["posts"],
                "replies": row["replies"],
                "boosts": row["boosts"],
                "reactions": row["reactions"],
                "group_messages": row["group_messages"],
                "polls": row["polls"],
            }

        return years

    def _get_global_stats(self):
        """Global counters, independent of the monthly breakdown.

        Bridge virtual feeds (and their profiles, posts and follows) are
        a connection helper, not real accounts, so they never count.
        """
        real_posts = Post.objects.exclude(bridge_urls_q("profile__feed"))
        return {
            "registered_feeds": Feed.objects.exclude(bridge_urls_q("url")).count(),
            "total_accounts": Profile.objects.exclude(bridge_urls_q("feed")).count(),
            "total_posts": real_posts.count(),
            "total_follows": Follow.objects.exclude(
                bridge_urls_q("followed__feed")
            ).count(),
            "active_groups": real_posts.exclude(group="")
            .values("group")
            .distinct()
            .count(),
        }
