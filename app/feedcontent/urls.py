from django.urls import path
from .views import FeedContentView

urlpatterns = [
    path("", FeedContentView.as_view(), name="feed-content"),
]
