"""
Middleware for adding CORS headers to all responses.
"""

import logging

logger = logging.getLogger(__name__)


class CORSMiddleware:
    """
    Middleware that adds CORS headers to all responses.

    This middleware ensures that:
    - All API responses are accessible from any origin (Access-Control-Allow-Origin: *)
    - Preflight OPTIONS requests are handled correctly
    - Common HTTP methods and headers are allowed
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = self._create_options_response()
        else:
            # Get the response from the view
            response = self.get_response(request)

        # Add CORS headers to all responses
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        response["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Requested-With"
        )
        response["Access-Control-Max-Age"] = "86400"  # 24 hours

        return response

    def _create_options_response(self):
        """Create a response for OPTIONS preflight requests"""
        from django.http import HttpResponse

        response = HttpResponse()
        response.status_code = 200
        return response
