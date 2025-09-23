from django.http import JsonResponse


def root_view(request):
    """Root endpoint with HATEOAS links"""
    return JsonResponse(
        {
            "type": "Success",
            "errors": [],
            "data": {
                "name": "Org Social Relay",
                "description": "P2P system for Org Social files",
            },
            "_links": {
                "self": {"href": "/", "method": "GET"},
                "feeds": {"href": "/feeds/", "method": "GET"},
                "add-feed": {"href": "/feeds/", "method": "POST"},
                "mentions": {
                    "href": "/mentions/?feed={feed_url}",
                    "method": "GET",
                    "templated": True,
                },
                "replies": {
                    "href": "/replies/?post={post_url}",
                    "method": "GET",
                    "templated": True,
                },
                "search": {
                    "href": "/search/?q={query}",
                    "method": "GET",
                    "templated": True,
                },
                "groups": {"href": "/groups/", "method": "GET"},
                "group-messages": {
                    "href": "/groups/{group_name}/",
                    "method": "GET",
                    "templated": True,
                },
                "join-group": {
                    "href": "/groups/{group_name}/members/?feed={feed_url}",
                    "method": "POST",
                    "templated": True,
                },
                "polls": {"href": "/polls/", "method": "GET"},
                "poll-votes": {
                    "href": "/polls/votes/?post={post_url}",
                    "method": "GET",
                    "templated": True,
                },
            },
        }
    )
