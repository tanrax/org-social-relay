from huey.contrib.djhuey import periodic_task, task, cron
from django.utils import timezone
from datetime import timedelta
import logging
import requests

logger = logging.getLogger(__name__)


@task()
def fetch_org_social_feed(profile_url):
    """
    Task to fetch and parse an Org Social feed from a URL
    """
    try:
        response = requests.get(profile_url, timeout=30)
        response.raise_for_status()
        content = response.text
        
        # Here you would implement the Org Social parsing logic
        logger.info(f"Successfully fetched feed from {profile_url}")
        return content
        
    except requests.RequestException as e:
        logger.error(f"Failed to fetch feed from {profile_url}: {e}")
        return None


@periodic_task(cron(minute='*/15'))  # Run every 15 minutes
def sync_all_feeds():
    """
    Periodic task to sync all followed feeds
    """
    from .models import Profile
    
    profiles = Profile.objects.all()
    logger.info(f"Starting sync for {profiles.count()} profiles")
    
    for profile in profiles:
        # Queue a task to fetch each profile's feed
        fetch_org_social_feed(profile.url)
    
    logger.info("Finished queuing feed sync tasks")


@periodic_task(cron(minute='0', hour='0'))  # Run daily at midnight
def cleanup_old_posts():
    """
    Periodic task to clean up old posts (older than 30 days)
    """
    from .models import Post
    
    cutoff_date = timezone.now() - timedelta(days=30)
    old_posts_count = Post.objects.filter(created_at__lt=cutoff_date).count()
    
    if old_posts_count > 0:
        deleted_count = Post.objects.filter(created_at__lt=cutoff_date).delete()[0]
        logger.info(f"Cleaned up {deleted_count} old posts")
    else:
        logger.info("No old posts to clean up")


@task()
def process_mentions_in_post(post_id):
    """
    Task to extract and process mentions from a post
    """
    from .models import Post
    from app.notifications.models import Mention
    import re
    
    try:
        post = Post.objects.get(id=post_id)
        
        # Extract mentions using regex for org-social links
        mention_pattern = r'\[\[org-social:([^\]]+)\]\[([^\]]+)\]\]'
        mentions = re.findall(mention_pattern, post.content)
        
        for profile_url, nickname in mentions:
            # Here you would look up the profile and create mention records
            logger.info(f"Found mention of {nickname} ({profile_url}) in post {post_id}")
            
        logger.info(f"Processed mentions for post {post_id}")
        
    except Post.DoesNotExist:
        logger.error(f"Post {post_id} not found")
    except Exception as e:
        logger.error(f"Error processing mentions for post {post_id}: {e}")