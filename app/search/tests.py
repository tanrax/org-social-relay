from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from app.feeds.models import Profile, Post


class SearchViewTest(TestCase):
    """Test cases for the SearchView API using Given/When/Then structure."""

    def setUp(self):
        self.client = APIClient()
        self.search_url = "/search/"

        # Create test profiles
        self.profile1 = Profile.objects.create(
            feed="https://example.com/social.org",
            title="Example Profile",
            nick="example_user",
            description="Test profile 1",
        )
        self.profile2 = Profile.objects.create(
            feed="https://test.com/social.org",
            title="Test Profile",
            nick="test_user",
            description="Test profile 2",
        )
        self.profile3 = Profile.objects.create(
            feed="https://third.com/social.org",
            title="Third Profile",
            nick="third_user",
            description="Test profile 3",
        )

        # Create test posts with different content and tags
        self.post1 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T12:00:00+00:00",
            content="This post is about Emacs and org-mode",
            tags="emacs org-mode",
        )

        self.post2 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T13:00:00+00:00",
            content="Learning Python programming language",
            tags="python programming",
        )

        self.post3 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T14:00:00+00:00",
            content="Django web framework with Python",
            tags="django python web",
        )

        self.post4 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T15:00:00+00:00",
            content="Emacs configuration and setup",
            tags="emacs configuration",
        )

        self.post5 = Post.objects.create(
            profile=self.profile2,
            post_id="2025-01-01T16:00:00+00:00",
            content="JavaScript and React development",
            tags="javascript react frontend",
        )

        # Add more posts for pagination testing
        self.post6 = Post.objects.create(
            profile=self.profile3,
            post_id="2025-01-01T17:00:00+00:00",
            content="Advanced Python concepts and patterns",
            tags="python advanced",
        )

        self.post7 = Post.objects.create(
            profile=self.profile1,
            post_id="2025-01-01T18:00:00+00:00",
            content="Python data science libraries",
            tags="python data-science",
        )

    def test_search_by_text_query_success(self):
        """Test GET /search/?q=<query> returns matching posts."""
        # Given: Posts with content containing "Emacs"

        # When: We search for "Emacs"
        response = self.client.get(self.search_url, {"q": "Emacs"})

        # Then: We should get posts containing "Emacs"
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Should return 2 posts (ordered by most recent first)
        data = response.data["data"]
        self.assertEqual(len(data), 2)
        expected_urls = [
            f"{self.profile1.feed}#{self.post4.post_id}",  # Most recent
            f"{self.profile1.feed}#{self.post1.post_id}",
        ]
        self.assertEqual(data, expected_urls)

        # Then: Meta should contain correct information
        meta = response.data["meta"]
        self.assertEqual(meta["query"], "Emacs")
        self.assertEqual(meta["total"], 2)
        self.assertEqual(meta["page"], 1)
        self.assertEqual(meta["perPage"], 10)
        self.assertFalse(meta["hasNext"])
        self.assertFalse(meta["hasPrevious"])
        self.assertIn("version", meta)

    def test_search_by_tag_success(self):
        """Test GET /search/?tag=<tag> returns posts with specific tag."""
        # Given: Posts with "python" tag

        # When: We search for tag "python"
        response = self.client.get(self.search_url, {"tag": "python"})

        # Then: We should get posts tagged with "python"
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["errors"], [])

        # Then: Should return 4 posts (all posts with python tag)
        data = response.data["data"]
        self.assertEqual(len(data), 4)
        # Check that all returned posts contain python-related content
        expected_posts = [self.post7, self.post6, self.post3, self.post2]  # Most recent first
        expected_urls = [f"{post.profile.feed}#{post.post_id}" for post in expected_posts]
        self.assertEqual(data, expected_urls)

        # Then: Meta should contain tag information
        meta = response.data["meta"]
        self.assertEqual(meta["tag"], "python")
        self.assertEqual(meta["total"], 4)

    def test_search_pagination(self):
        """Test search pagination works correctly."""
        # Given: Multiple posts and small page size

        # When: We search with perPage=2 and page=1 for content that appears in multiple posts
        response = self.client.get(self.search_url, {"q": "Python", "perPage": 2, "page": 1})

        # Then: We should get first 2 results
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(len(data), 2)

        # Then: Meta should show pagination info
        meta = response.data["meta"]
        self.assertEqual(meta["page"], 1)
        self.assertEqual(meta["perPage"], 2)
        self.assertTrue(meta["hasNext"])
        self.assertFalse(meta["hasPrevious"])
        self.assertIsNotNone(meta["links"]["next"])
        self.assertIsNone(meta["links"]["previous"])

        # When: We request page 2
        response2 = self.client.get(self.search_url, {"q": "Python", "perPage": 2, "page": 2})

        # Then: We should get next 2 results
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        data2 = response2.data["data"]
        self.assertEqual(len(data2), 2)

        # Then: Results should be different from page 1
        self.assertNotEqual(data, data2)

    def test_search_case_insensitive(self):
        """Test that search is case insensitive."""
        # Given: Posts with mixed case content

        # When: We search with lowercase
        response1 = self.client.get(self.search_url, {"q": "emacs"})

        # When: We search with uppercase
        response2 = self.client.get(self.search_url, {"q": "EMACS"})

        # Then: Both should return same results
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response1.data["data"], response2.data["data"])

    def test_search_no_results(self):
        """Test search with no matching results."""
        # Given: Search term that doesn't exist

        # When: We search for non-existent term
        response = self.client.get(self.search_url, {"q": "nonexistent"})

        # Then: We should get empty results
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "Success")
        self.assertEqual(response.data["data"], [])
        self.assertEqual(response.data["meta"]["total"], 0)

    def test_search_missing_parameters(self):
        """Test that missing search parameters return 400 error."""
        # Given: Search endpoint

        # When: We request without q or tag parameters
        response = self.client.get(self.search_url)

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("required", response.data["errors"][0])

    def test_search_invalid_page_number(self):
        """Test invalid page numbers return appropriate errors."""
        # Given: Search with valid query

        # When: We request page 0
        response = self.client.get(self.search_url, {"q": "test", "page": 0})

        # Then: Should return 400 error
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["type"], "Error")
        self.assertIn("Page number must be 1 or greater", response.data["errors"][0])

        # When: We request page beyond available results
        response2 = self.client.get(self.search_url, {"q": "emacs", "page": 999})

        # Then: Should return 400 error
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response2.data["type"], "Error")
        self.assertIn("does not exist", response2.data["errors"][0])

    def test_search_per_page_limits(self):
        """Test perPage parameter respects maximum limit."""
        # Given: Search with large perPage value

        # When: We request more than 50 items per page
        response = self.client.get(self.search_url, {"q": "post", "perPage": 100})

        # Then: Should be limited to 50
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        meta = response.data["meta"]
        self.assertEqual(meta["perPage"], 50)

    def test_search_response_format_compliance(self):
        """Test search response format compliance with README specification."""
        # Given: Search with valid parameters

        # When: We perform a search
        response = self.client.get(self.search_url, {"q": "emacs"})

        # Then: Response should match expected format
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertIn("errors", response.data)
        self.assertIn("data", response.data)
        self.assertIn("meta", response.data)
        self.assertEqual(response.data["type"], "Success")
        self.assertIsInstance(response.data["errors"], list)
        self.assertIsInstance(response.data["data"], list)
        self.assertIsInstance(response.data["meta"], dict)

        # Then: Meta should contain all required fields
        meta = response.data["meta"]
        required_fields = ["version", "query", "total", "page", "perPage", "hasNext", "hasPrevious", "links"]
        for field in required_fields:
            self.assertIn(field, meta)

    def test_search_view_methods_allowed(self):
        """Test that only GET method is allowed on search endpoint."""
        # Given: A valid search URL
        params = {"q": "test"}

        # When: We try different HTTP methods
        post_response = self.client.post(self.search_url, params)
        put_response = self.client.put(self.search_url, params)
        delete_response = self.client.delete(self.search_url, params)
        patch_response = self.client.patch(self.search_url, params)

        # Then: Unsupported methods should return 405
        self.assertEqual(post_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(put_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_search_url_generation(self):
        """Test that pagination URLs are generated correctly."""
        # Given: Search with pagination

        # When: We search with specific parameters
        response = self.client.get(self.search_url, {"q": "post", "perPage": 2, "page": 1})

        # Then: Links should be properly formatted
        meta = response.data["meta"]
        links = meta["links"]

        if links["next"]:
            self.assertIn("q=post", links["next"])
            self.assertIn("perPage=2", links["next"])
            self.assertIn("page=2", links["next"])

    def test_search_both_content_and_tags(self):
        """Test that search looks in both content and tags fields."""
        # Given: Post with "emacs" in content and "configuration" in tags

        # When: We search for "configuration"
        response = self.client.get(self.search_url, {"q": "configuration"})

        # Then: Should find post4 which has "configuration" in tags
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        expected_url = f"{self.profile1.feed}#{self.post4.post_id}"
        self.assertIn(expected_url, data)

    def test_search_tag_vs_query_difference(self):
        """Test difference between tag search and text query search."""
        # Given: Posts with tags

        # When: We search by tag "emacs"
        tag_response = self.client.get(self.search_url, {"tag": "emacs"})

        # When: We search by query "emacs"
        query_response = self.client.get(self.search_url, {"q": "emacs"})

        # Then: Both should return results but meta should be different
        self.assertEqual(tag_response.status_code, status.HTTP_200_OK)
        self.assertEqual(query_response.status_code, status.HTTP_200_OK)

        # Then: Meta should indicate different search types
        self.assertIn("tag", tag_response.data["meta"])
        self.assertIn("query", query_response.data["meta"])