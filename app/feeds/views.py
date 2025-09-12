from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.core.paginator import Paginator

from .models import Profile, Post, Follow
from app.groups.models import Group, GroupMembership
from app.notifications.models import Mention, Reply


class FeedsView(APIView):
    """List feeds or add new feed"""
    
    def get(self, request):
        feeds = Profile.objects.all().values_list('url', flat=True)
        return Response({
            "type": "Success",
            "errors": [],
            "data": list(feeds)
        }, status=status.HTTP_200_OK)
    
    def post(self, request):
        feed_url = request.data.get('feed')
        
        if not feed_url or not feed_url.strip():
            return Response({
                "type": "Error",
                "errors": ["Feed URL is required"],
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create or get profile
        profile, created = Profile.objects.get_or_create(
            url=feed_url,
            defaults={'nick': 'Unknown', 'title': 'Unknown Feed'}
        )
        
        return Response({
            "type": "Success",
            "errors": [],
            "data": {
                "feed": feed_url
            }
        }, status=status.HTTP_201_CREATED)


class MentionsView(APIView):
    """Get mentions for a given feed"""
    
    def get(self, request):
        feed_url = request.GET.get('feed')
        
        if not feed_url:
            return Response({
                "type": "Error",
                "errors": ["feed parameter is required"],
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            profile = Profile.objects.get(url=feed_url)
            mentions = Mention.objects.filter(mentioned_profile=profile).order_by('-created_at')
            
            mention_posts = []
            for mention in mentions:
                post_url = f"{mention.post.profile.url}#{mention.post.post_id}"
                mention_posts.append(post_url)
            
            return Response({
                "type": "Success",
                "errors": [],
                "data": mention_posts,
                "meta": {
                    "feed": feed_url,
                    "total": len(mention_posts),
                    "version": "123"
                }
            }, status=status.HTTP_200_OK)
            
        except Profile.DoesNotExist:
            return Response({
                "type": "Error",
                "errors": ["Feed not found"],
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)


class RepliesView(APIView):
    """Get replies for a given post"""
    
    def get(self, request):
        post_param = request.GET.get('post')
        
        if not post_param:
            return Response({
                "type": "Error",
                "errors": ["post parameter is required"],
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Parse post URL to get profile URL and post ID
            if '#' not in post_param:
                return Response({
                    "type": "Error",
                    "errors": ["Invalid post URL format"],
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            profile_url, post_id = post_param.rsplit('#', 1)
            
            # Find replies to this post
            replies = Post.objects.filter(reply_to=post_param).order_by('created_at')
            
            # Build tree structure (simplified for now)
            reply_data = []
            for reply in replies:
                reply_url = f"{reply.profile.url}#{reply.post_id}"
                reply_data.append({
                    "post": reply_url,
                    "children": []  # Would need recursive logic for nested replies
                })
            
            return Response({
                "type": "Success",
                "errors": [],
                "data": reply_data,
                "meta": {
                    "parent": post_param,
                    "version": "123"
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "type": "Error",
                "errors": [str(e)],
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SearchView(APIView):
    """Search posts by query or tag"""
    
    def get(self, request):
        query = request.GET.get('q', '')
        tag = request.GET.get('tag', '')
        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('perPage', 10)), 50)
        
        if not query and not tag:
            return Response({
                "type": "Error",
                "errors": ["Either 'q' or 'tag' parameter is required"],
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)
        
        posts = Post.objects.all()
        
        if query:
            posts = posts.filter(Q(content__icontains=query) | Q(tags__icontains=query))
            search_term = query
        else:
            posts = posts.filter(tags__icontains=tag)
            search_term = tag
        
        paginator = Paginator(posts.order_by('-created_at'), per_page)
        page_obj = paginator.get_page(page)
        
        results = []
        for post in page_obj:
            post_url = f"{post.profile.url}#{post.post_id}"
            results.append(post_url)
        
        return Response({
            "type": "Success",
            "errors": [],
            "data": results,
            "meta": {
                "version": "123",
                "query": search_term,
                "total": paginator.count,
                "page": page,
                "perPage": per_page,
                "hasNext": page_obj.has_next(),
                "hasPrevious": page_obj.has_previous(),
                "links": {
                    "next": f"/search?q={search_term}&page={page + 1}" if page_obj.has_next() else None,
                    "previous": f"/search?q={search_term}&page={page - 1}" if page_obj.has_previous() else None
                }
            }
        }, status=status.HTTP_200_OK)


class GroupsView(APIView):
    """List all groups"""
    
    def get(self, request):
        groups = Group.objects.all()
        
        groups_data = []
        for group in groups:
            groups_data.append({
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "members": group.memberships.count(),
                "posts": group.group_posts.count()
            })
        
        return Response({
            "type": "Success",
            "errors": [],
            "data": groups_data
        }, status=status.HTTP_200_OK)


class GroupMembersView(APIView):
    """Register as group member"""
    
    def post(self, request, group_id):
        feed_url = request.GET.get('feed')
        
        if not feed_url:
            return Response({
                "type": "Error",
                "errors": ["feed parameter is required"],
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            group = Group.objects.get(id=group_id)
            profile = Profile.objects.get(url=feed_url)
            
            # Create membership if it doesn't exist
            membership, created = GroupMembership.objects.get_or_create(
                group=group,
                profile=profile
            )
            
            return Response({
                "type": "Success",
                "errors": [],
                "data": {
                    "group": group.name,
                    "feed": feed_url
                }
            }, status=status.HTTP_201_CREATED)
            
        except Group.DoesNotExist:
            return Response({
                "type": "Error",
                "errors": ["Group not found"],
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)
        except Profile.DoesNotExist:
            return Response({
                "type": "Error",
                "errors": ["Feed not found"],
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)


class GroupMessagesView(APIView):
    """Get messages from a group"""
    
    def get(self, request, group_id):
        try:
            group = Group.objects.get(id=group_id)
            group_posts = group.group_posts.all().order_by('-shared_at')
            
            messages_data = []
            for group_post in group_posts:
                post_url = f"{group_post.post.profile.url}#{group_post.post.post_id}"
                messages_data.append({
                    "post": post_url,
                    "children": []  # Would need logic for replies within the group
                })
            
            return Response({
                "type": "Success",
                "errors": [],
                "data": messages_data,
                "meta": {
                    "group": group.name,
                    "total": len(messages_data),
                    "version": "123"
                }
            }, status=status.HTTP_200_OK)
            
        except Group.DoesNotExist:
            return Response({
                "type": "Error",
                "errors": ["Group not found"],
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)
