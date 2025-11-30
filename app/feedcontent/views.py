from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging
import requests

from app.feeds.models import Profile

logger = logging.getLogger(__name__)


class FeedContentView(APIView):
    """Get raw content of an Org Social feed file"""

    def get(self, request):
        feed_url = request.query_params.get("feed")

        if not feed_url or not feed_url.strip():
            return Response(
                {
                    "type": "Error",
                    "errors": ["Feed URL parameter is required"],
                    "data": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        feed_url = feed_url.strip()

        # Check if the feed is registered in the relay
        try:
            Profile.objects.get(feed=feed_url)
        except Profile.DoesNotExist:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Feed not found in relay"],
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Fetch the feed content from the source URL
        try:
            response = requests.get(feed_url, timeout=10)
            response.raise_for_status()

            # Decode content as UTF-8
            content = response.content.decode("utf-8")

            # URL encode the feed_url for the self link
            from urllib.parse import quote

            encoded_feed_url = quote(feed_url, safe="")

            response_data = {
                "type": "Success",
                "errors": [],
                "data": {"content": content},
                "_links": {
                    "self": {
                        "href": f"/feed-content/?feed={encoded_feed_url}",
                        "method": "GET",
                    }
                },
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except requests.exceptions.Timeout:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Request timeout: Feed server did not respond in time"],
                    "data": None,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except requests.exceptions.ConnectionError:
            return Response(
                {
                    "type": "Error",
                    "errors": ["Connection error: Could not reach feed server"],
                    "data": None,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except requests.exceptions.HTTPError as e:
            return Response(
                {
                    "type": "Error",
                    "errors": [f"HTTP error: {e}"],
                    "data": None,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as e:
            logger.error(f"Failed to fetch feed content from {feed_url}: {e}")
            return Response(
                {
                    "type": "Error",
                    "errors": ["Failed to fetch feed content"],
                    "data": None,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
