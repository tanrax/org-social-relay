"""
Middleware for adding global HTTP caching headers to all responses.
"""

import logging
from app.feeds.models import RelayMetadata

logger = logging.getLogger(__name__)


class RelayMetadataMiddleware:
    """
    Middleware that adds global ETag and Last-Modified headers to all responses.

    This middleware ensures that:
    - All API responses get consistent caching headers
    - Headers are added even when serving cached responses
    - The ETag and Last-Modified come from RelayMetadata (updated by scan_feeds)
    - All clients see the same cache version across all endpoints
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get the response from the view
        response = self.get_response(request)

        # Add global relay headers to successful responses
        # Only add to 200-299 status codes (successful responses)
        if 200 <= response.status_code < 300:
            try:
                etag, last_modified = RelayMetadata.get_global_metadata()
                response["ETag"] = f'"{etag}"'
                response["Last-Modified"] = last_modified.strftime(
                    "%a, %d %b %Y %H:%M:%S GMT"
                )
            except Exception as e:
                # Log error but don't fail the request
                logger.warning(f"Failed to add relay metadata headers: {e}")

        return response
