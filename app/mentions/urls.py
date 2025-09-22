from django.urls import path
from .views import MentionsView

app_name = "mentions"

urlpatterns = [
    path("", MentionsView.as_view(), name="mentions"),
]