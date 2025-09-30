from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from django.db.models import Q
from django.core.paginator import Paginator
import logging
import hashlib

from app.feeds.models import Post

logger = logging.getLogger(__name__)


class SearchView(APIView):
    """Search posts by free text or tags with pagination"""

    def get(self, request):
        query = request.query_params.get("q")
        tag = request.query_params.get("tag")
        page = int(request.query_params.get("page", 1))
        per_page = min(int(request.query_params.get("perPage", 10)), 50)

        # Validate search parameters
        if not query and not tag:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Either 'q' (query) or 'tag' parameter is required"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page < 1:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Page number must be 1 or greater"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build cache key
        search_term = query if query else f"tag:{tag}"
        cache_key = f"search_{hashlib.md5(search_term.encode()).hexdigest()[:8]}_{page}_{per_page}"
        cached_response = cache.get(cache_key)

        if cached_response is not None:
            return Response(cached_response, status=status.HTTP_200_OK)

        # Build search query
        posts_query = Post.objects.select_related("profile").order_by("-created_at")

        if query:
            # Search in content using case-insensitive contains
            posts_query = posts_query.filter(
                Q(content__icontains=query) | Q(tags__icontains=query)
            )
            search_type = "query"
            search_value = query
        else:
            # Search by specific tag
            posts_query = posts_query.filter(tags__icontains=tag)
            search_type = "tag"
            search_value = tag

        # Get total count for pagination
        total_posts = posts_query.count()

        # Apply pagination
        paginator = Paginator(posts_query, per_page)

        if page > paginator.num_pages and total_posts > 0:
            return Response(
                {
                    "type": "Error",
                    "errors": [
                        f"Page {page} does not exist. Maximum page is {paginator.num_pages}"
                    ],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        posts_page = paginator.get_page(page)

        # Build data array with post URLs
        data = []
        for post in posts_page:
            post_url = f"{post.profile.feed}#{post.post_id}"
            data.append(post_url)

        # Generate pagination links
        base_url = "/search"
        if query:
            base_url += f"?q={query}"
        else:
            base_url += f"?tag={tag}"

        if per_page != 10:
            base_url += f"&perPage={per_page}"

        # Generate version hash based on search parameters and total results
        version_string = f"{search_term}_{total_posts}_{posts_query.first().updated_at.isoformat() if posts_query.exists() else 'empty'}"
        version = hashlib.md5(version_string.encode()).hexdigest()[:8]

        # Build response
        response_data = {
            "type": "Success",
            "errors": [],
            "data": data,
            "meta": {
                "version": version,
                search_type: search_value,
                "total": total_posts,
                "page": page,
                "perPage": per_page,
                "hasNext": posts_page.has_next(),
                "hasPrevious": posts_page.has_previous(),
            },
            "_links": {
                "self": {"href": f"{base_url}&page={page}", "method": "GET"},
                "next": {"href": f"{base_url}&page={page + 1}", "method": "GET"}
                if posts_page.has_next()
                else None,
                "previous": {"href": f"{base_url}&page={page - 1}", "method": "GET"}
                if posts_page.has_previous()
                else None,
            },
        }

        # Cache permanently (will be cleared by scan_feeds task)
        cache.set(cache_key, response_data, None)

        return Response(response_data, status=status.HTTP_200_OK)
