from django.urls import path
from .views import RepliesView

app_name = "replies"

urlpatterns = [
    path("", RepliesView.as_view(), name="replies"),
]
