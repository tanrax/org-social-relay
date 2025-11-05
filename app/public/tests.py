from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status


class RootViewTest(TestCase):
    """Test cases for the root endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.root_url = "/"

    def test_root_endpoint_success(self):
        """Test GET / returns success response with HATEOAS links."""
        # Given: The root endpoint

        # When: We request the root endpoint
        response = self.client.get(self.root_url)

        # Then: We should get success response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["type"], "Success")
        self.assertEqual(response.json()["errors"], [])

        # Then: Should have data with name and description
        data = response.json()["data"]
        self.assertIn("name", data)
        self.assertIn("description", data)
        self.assertEqual(data["name"], "Org Social Relay")

    def test_root_endpoint_hateoas_links(self):
        """Test GET / returns all expected HATEOAS links."""
        # Given: The root endpoint

        # When: We request the root endpoint
        response = self.client.get(self.root_url)

        # Then: Should have _links with all endpoints
        links = response.json()["_links"]
        expected_links = [
            "self",
            "feeds",
            "add-feed",
            "mentions",
            "replies",
            "notifications",
            "reactions",
            "replies-to",
            "search",
            "groups",
            "group-messages",
            "join-group",
            "polls",
            "poll-votes",
        ]

        for link_name in expected_links:
            self.assertIn(link_name, links, f"Missing link: {link_name}")

    def test_root_endpoint_has_caching_headers(self):
        """Test GET / returns ETag and Last-Modified headers."""
        # Given: The root endpoint

        # When: We request the root endpoint
        response = self.client.get(self.root_url)

        # Then: Should have ETag and Last-Modified headers
        self.assertIn("ETag", response)
        self.assertIn("Last-Modified", response)

        # Then: ETag should be properly formatted (quoted)
        etag = response["ETag"]
        self.assertTrue(etag.startswith('"') and etag.endswith('"'))

    def test_root_endpoint_consistent_etag(self):
        """Test GET / returns consistent ETag for same content."""
        # Given: The root endpoint

        # When: We request the root endpoint multiple times
        response1 = self.client.get(self.root_url)
        response2 = self.client.get(self.root_url)

        # Then: ETag should be the same (content is static)
        self.assertEqual(response1["ETag"], response2["ETag"])

    def test_root_endpoint_response_format_compliance(self):
        """Test root endpoint response format compliance."""
        # Given: The root endpoint

        # When: We request the root endpoint
        response = self.client.get(self.root_url)

        # Then: Response should match expected format
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIn("type", response_data)
        self.assertIn("errors", response_data)
        self.assertIn("data", response_data)
        self.assertIn("_links", response_data)
        self.assertIsInstance(response_data["errors"], list)
        self.assertIsInstance(response_data["data"], dict)
        self.assertIsInstance(response_data["_links"], dict)

    def test_root_endpoint_all_methods_return_same_content(self):
        """Test that root endpoint returns same content for all HTTP methods."""
        # Given: The root endpoint

        # When: We try different HTTP methods
        get_response = self.client.get(self.root_url)
        post_response = self.client.post(self.root_url)

        # Then: All methods should return 200 with same content
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(post_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.json()["type"], "Success")
        self.assertEqual(post_response.json()["type"], "Success")
