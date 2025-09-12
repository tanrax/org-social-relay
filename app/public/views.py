from django.http import JsonResponse


def root_view(request):
    """Root endpoint with HATEOAS links"""
    return JsonResponse({
        "_links": [
            {"rel": "self", "href": "/", "method": "GET"},
            {"rel": "list-feeds", "href": "/feeds", "method": "GET"},
            {"rel": "add-feed", "href": "/feeds", "method": "POST"},
            {"rel": "get-mentions", "href": "/mentions/?feed={url feed}", "method": "GET"},
            {"rel": "get-replies", "href": "/replies/?post={url post}", "method": "GET"},
            {"rel": "search", "href": "/search?q={query}", "method": "GET"},
            {"rel": "list-groups", "href": "/groups", "method": "GET"},
            {"rel": "get-group-messages", "href": "/groups/{group id}/messages", "method": "GET"},
            {"rel": "register-group-member", "href": "/groups/{group id}/members?feed={url feed}", "method": "POST"}
        ]
    })