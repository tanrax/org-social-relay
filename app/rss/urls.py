from django.urls import path
from .views import LatestPostsFeed

urlpatterns = [
    path("", LatestPostsFeed(), name="rss_feed"),
]
