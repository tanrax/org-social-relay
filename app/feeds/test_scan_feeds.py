from django.test import TestCase
from app.feeds.models import Feed, Profile, Post


class PostDeletionDetectionTest(TestCase):
    """Test cases for detecting and removing deleted posts."""

    def setUp(self):
        """Set up test fixtures."""
        self.feed_url = "https://example.com/social.org"
        self.feed = Feed.objects.create(url=self.feed_url)
        self.profile = Profile.objects.create(
            feed=self.feed_url,
            nick="test_user",
            title="Test User",
        )

    def test_detect_deleted_posts(self):
        """Test deletion detection logic."""
        # Given: Profile has 3 posts in database
        Post.objects.create(
            profile=self.profile, post_id="2025-01-01T10:00:00+0100", content="Post 1"
        )
        Post.objects.create(
            profile=self.profile, post_id="2025-01-02T10:00:00+0100", content="Post 2"
        )
        Post.objects.create(
            profile=self.profile, post_id="2025-01-03T10:00:00+0100", content="Post 3"
        )

        # When: Current feed only has 2 posts (simulating one was deleted)
        current_post_ids = {"2025-01-01T10:00:00+0100", "2025-01-03T10:00:00+0100"}

        # Get existing posts from database
        existing_posts = Post.objects.filter(profile=self.profile)
        existing_post_ids = set(existing_posts.values_list("post_id", flat=True))

        # Find deleted posts
        deleted_post_ids = existing_post_ids - current_post_ids

        # Then: Should detect one deleted post
        self.assertEqual(len(deleted_post_ids), 1)
        self.assertIn("2025-01-02T10:00:00+0100", deleted_post_ids)

        # When: Delete the posts that no longer exist
        deleted_count = Post.objects.filter(
            profile=self.profile, post_id__in=deleted_post_ids
        ).delete()[0]

        # Then: One post should be deleted
        self.assertEqual(deleted_count, 1)

        # Then: Only 2 posts should remain
        remaining_posts = Post.objects.filter(profile=self.profile)
        self.assertEqual(remaining_posts.count(), 2)

        # Then: Deleted post should not exist
        self.assertFalse(
            Post.objects.filter(
                profile=self.profile, post_id="2025-01-02T10:00:00+0100"
            ).exists()
        )

        # Then: Other posts should still exist
        self.assertTrue(
            Post.objects.filter(
                profile=self.profile, post_id="2025-01-01T10:00:00+0100"
            ).exists()
        )
        self.assertTrue(
            Post.objects.filter(
                profile=self.profile, post_id="2025-01-03T10:00:00+0100"
            ).exists()
        )

    def test_no_posts_deleted_when_all_present(self):
        """Test that no posts are deleted when all posts are still in feed."""
        # Given: Profile has 2 posts
        Post.objects.create(
            profile=self.profile, post_id="2025-01-01T10:00:00+0100", content="Post 1"
        )
        Post.objects.create(
            profile=self.profile, post_id="2025-01-02T10:00:00+0100", content="Post 2"
        )

        # When: Current feed still has both posts
        current_post_ids = {"2025-01-01T10:00:00+0100", "2025-01-02T10:00:00+0100"}

        # Get existing posts
        existing_posts = Post.objects.filter(profile=self.profile)
        existing_post_ids = set(existing_posts.values_list("post_id", flat=True))

        # Find deleted posts
        deleted_post_ids = existing_post_ids - current_post_ids

        # Then: No posts should be detected as deleted
        self.assertEqual(len(deleted_post_ids), 0)

        # Then: Both posts should still exist
        self.assertEqual(Post.objects.filter(profile=self.profile).count(), 2)

    def test_all_posts_deleted(self):
        """Test handling when all posts are deleted from feed."""
        # Given: Profile has 2 posts
        Post.objects.create(
            profile=self.profile, post_id="2025-01-01T10:00:00+0100", content="Post 1"
        )
        Post.objects.create(
            profile=self.profile, post_id="2025-01-02T10:00:00+0100", content="Post 2"
        )

        # When: Current feed has no posts
        current_post_ids = set()

        # Get existing posts
        existing_posts = Post.objects.filter(profile=self.profile)
        existing_post_ids = set(existing_posts.values_list("post_id", flat=True))

        # Find deleted posts
        deleted_post_ids = existing_post_ids - current_post_ids

        # Then: All posts should be detected as deleted
        self.assertEqual(len(deleted_post_ids), 2)

        # When: Delete all posts
        deleted_count = Post.objects.filter(
            profile=self.profile, post_id__in=deleted_post_ids
        ).delete()[0]

        # Then: 2 posts should be deleted
        self.assertEqual(deleted_count, 2)

        # Then: No posts should remain
        self.assertEqual(Post.objects.filter(profile=self.profile).count(), 0)

    def test_multiple_posts_deleted(self):
        """Test handling when multiple posts are deleted."""
        # Given: Profile has 5 posts
        for i in range(1, 6):
            Post.objects.create(
                profile=self.profile,
                post_id=f"2025-01-0{i}T10:00:00+0100",
                content=f"Post {i}",
            )

        # When: Current feed only has 2 posts (3 were deleted)
        current_post_ids = {"2025-01-01T10:00:00+0100", "2025-01-05T10:00:00+0100"}

        # Get existing posts
        existing_posts = Post.objects.filter(profile=self.profile)
        existing_post_ids = set(existing_posts.values_list("post_id", flat=True))

        # Find deleted posts
        deleted_post_ids = existing_post_ids - current_post_ids

        # Then: 3 posts should be detected as deleted
        self.assertEqual(len(deleted_post_ids), 3)

        # When: Delete them
        deleted_count = Post.objects.filter(
            profile=self.profile, post_id__in=deleted_post_ids
        ).delete()[0]

        # Then: 3 posts should be deleted
        self.assertEqual(deleted_count, 3)

        # Then: Only 2 posts should remain
        self.assertEqual(Post.objects.filter(profile=self.profile).count(), 2)
