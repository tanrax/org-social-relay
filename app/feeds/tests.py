import pytest
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from .models import Profile, Post, Follow
from app.groups.models import Group, GroupMembership
from app.notifications.models import Mention, Reply


@pytest.mark.django_db
class FeedsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.feeds_url = reverse('feeds')
        
        # Create some test profiles
        self.profile1 = Profile.objects.create(
            url='https://example.com/social.org',
            nick='testuser1',
            title='Test User 1'
        )
        self.profile2 = Profile.objects.create(
            url='https://another.com/social.org',
            nick='testuser2',
            title='Test User 2'
        )

    def test_list_feeds_success(self):
        """Test GET /feeds returns all feed URLs"""
        response = self.client.get(self.feeds_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(response.data['errors'], [])
        self.assertIn('https://example.com/social.org', response.data['data'])
        self.assertIn('https://another.com/social.org', response.data['data'])
        self.assertEqual(len(response.data['data']), 2)

    def test_list_feeds_empty(self):
        """Test GET /feeds returns empty list when no feeds exist"""
        Profile.objects.all().delete()
        response = self.client.get(self.feeds_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(response.data['errors'], [])
        self.assertEqual(response.data['data'], [])

    def test_add_feed_success(self):
        """Test POST /feeds successfully adds a new feed"""
        new_feed_url = 'https://newsite.com/social.org'
        data = {'feed': new_feed_url}
        
        response = self.client.post(self.feeds_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(response.data['errors'], [])
        self.assertEqual(response.data['data']['feed'], new_feed_url)
        
        # Verify the profile was created
        profile = Profile.objects.get(url=new_feed_url)
        self.assertEqual(profile.nick, 'Unknown')
        self.assertEqual(profile.title, 'Unknown Feed')

    def test_add_feed_duplicate(self):
        """Test POST /feeds with existing feed URL"""
        existing_url = self.profile1.url
        data = {'feed': existing_url}
        
        response = self.client.post(self.feeds_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(response.data['errors'], [])
        self.assertEqual(response.data['data']['feed'], existing_url)
        
        # Verify no duplicate was created
        self.assertEqual(Profile.objects.filter(url=existing_url).count(), 1)

    def test_add_feed_missing_url(self):
        """Test POST /feeds without feed URL parameter"""
        data = {}
        response = self.client.post(self.feeds_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['type'], 'Error')
        self.assertEqual(response.data['errors'], ['Feed URL is required'])
        self.assertEqual(response.data['data'], None)

    def test_add_feed_empty_url(self):
        """Test POST /feeds with empty feed URL"""
        data = {'feed': ''}
        response = self.client.post(self.feeds_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['type'], 'Error')
        self.assertEqual(response.data['errors'], ['Feed URL is required'])
        self.assertEqual(response.data['data'], None)

    def test_add_feed_with_whitespace_url(self):
        """Test POST /feeds with whitespace-only feed URL"""
        data = {'feed': '   '}
        response = self.client.post(self.feeds_url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['type'], 'Error')
        self.assertEqual(response.data['errors'], ['Feed URL is required'])
        self.assertEqual(response.data['data'], None)


@pytest.mark.django_db
class MentionsViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.mentions_url = reverse('mentions')
        
        # Create test data
        self.profile1 = Profile.objects.create(
            url='https://example.com/social.org',
            nick='testuser1',
            title='Test User 1'
        )
        self.profile2 = Profile.objects.create(
            url='https://another.com/social.org',
            nick='testuser2',
            title='Test User 2'
        )
        
        # Create a post
        self.post = Post.objects.create(
            profile=self.profile2,
            post_id='2024-01-01T12:00:00Z',
            content='Hello @testuser1!'
        )
        
        # Create a mention
        self.mention = Mention.objects.create(
            post=self.post,
            mentioned_profile=self.profile1
        )

    def test_get_mentions_success(self):
        """Test GET /mentions/ returns mentions for a feed"""
        response = self.client.get(self.mentions_url, {'feed': self.profile1.url})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(response.data['errors'], [])
        expected_post_url = f"{self.profile2.url}#{self.post.post_id}"
        self.assertIn(expected_post_url, response.data['data'])
        self.assertEqual(response.data['meta']['feed'], self.profile1.url)
        self.assertEqual(response.data['meta']['total'], 1)
        self.assertEqual(response.data['meta']['version'], '123')

    def test_get_mentions_missing_feed_param(self):
        """Test GET /mentions/ without feed parameter"""
        response = self.client.get(self.mentions_url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['type'], 'Error')
        self.assertEqual(response.data['errors'], ['feed parameter is required'])
        self.assertEqual(response.data['data'], None)

    def test_get_mentions_feed_not_found(self):
        """Test GET /mentions/ with non-existent feed"""
        response = self.client.get(self.mentions_url, {'feed': 'https://nonexistent.com/social.org'})
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['type'], 'Error')
        self.assertEqual(response.data['errors'], ['Feed not found'])
        self.assertEqual(response.data['data'], None)

    def test_get_mentions_no_mentions(self):
        """Test GET /mentions/ for feed with no mentions"""
        response = self.client.get(self.mentions_url, {'feed': self.profile2.url})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(response.data['errors'], [])
        self.assertEqual(response.data['data'], [])
        self.assertEqual(response.data['meta']['feed'], self.profile2.url)
        self.assertEqual(response.data['meta']['total'], 0)


@pytest.mark.django_db
class SearchViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.search_url = reverse('search')
        
        # Create test data
        self.profile = Profile.objects.create(
            url='https://example.com/social.org',
            nick='testuser',
            title='Test User'
        )
        
        self.post1 = Post.objects.create(
            profile=self.profile,
            post_id='2024-01-01T12:00:00Z',
            content='Hello world!',
            tags='greeting test'
        )
        
        self.post2 = Post.objects.create(
            profile=self.profile,
            post_id='2024-01-01T13:00:00Z',
            content='This is a test post',
            tags='test python'
        )

    def test_search_by_query_content(self):
        """Test search by content query"""
        response = self.client.get(self.search_url, {'q': 'Hello'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(len(response.data['data']), 1)
        expected_url = f"{self.profile.url}#{self.post1.post_id}"
        self.assertIn(expected_url, response.data['data'])

    def test_search_by_tag(self):
        """Test search by tag"""
        response = self.client.get(self.search_url, {'tag': 'test'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type'], 'Success')
        self.assertEqual(len(response.data['data']), 2)  # Both posts have 'test' tag

    def test_search_missing_parameters(self):
        """Test search without q or tag parameter"""
        response = self.client.get(self.search_url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['type'], 'Error')
        self.assertEqual(response.data['errors'], ["Either 'q' or 'tag' parameter is required"])
        self.assertEqual(response.data['data'], None)

    def test_search_pagination(self):
        """Test search with pagination"""
        response = self.client.get(self.search_url, {'q': 'test', 'page': 1, 'perPage': 1})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['meta']['page'], 1)
        self.assertEqual(response.data['meta']['perPage'], 1)
        self.assertEqual(response.data['meta']['total'], 2)  # Both posts contain 'test' in content or tags
        self.assertTrue(response.data['meta']['hasNext'])  # Should have next page since total=2 and perPage=1


@pytest.mark.django_db  
class IntegrationTest(TestCase):
    """Integration tests for the feed workflow"""
    
    def setUp(self):
        self.client = APIClient()

    def test_complete_feed_workflow(self):
        """Test the complete workflow: add feed -> list feeds -> verify feed exists"""
        feeds_url = reverse('feeds')
        feed_url = 'https://integration-test.com/social.org'
        
        # Step 1: Add a new feed
        add_response = self.client.post(feeds_url, {'feed': feed_url})
        self.assertEqual(add_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(add_response.data['data']['feed'], feed_url)
        
        # Step 2: List all feeds
        list_response = self.client.get(feeds_url)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(feed_url, list_response.data['data'])
        
        # Step 3: Verify the profile was created correctly
        profile = Profile.objects.get(url=feed_url)
        self.assertEqual(profile.url, feed_url)
        self.assertEqual(profile.nick, 'Unknown')
        self.assertEqual(profile.title, 'Unknown Feed')