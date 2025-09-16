from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Feed


class FeedsView(APIView):
    """List feeds or add new feed"""

    def get(self, request):
        feeds = Feed.objects.all().values_list("url", flat=True)
        return Response(
            {"type": "Success", "errors": [], "data": list(feeds)},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        feed_url = request.data.get("feed")

        if not feed_url or not feed_url.strip():
            return Response(
                {"type": "Error", "errors": ["Feed URL is required"], "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create or get feed
        feed, created = Feed.objects.get_or_create(url=feed_url.strip())

        # Return appropriate status code
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK

        return Response(
            {"type": "Success", "errors": [], "data": {"feed": feed_url.strip()}},
            status=response_status,
        )
