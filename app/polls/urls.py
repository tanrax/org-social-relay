from django.urls import path
from .views import PollsView, PollVotesView

app_name = "polls"

urlpatterns = [
    path("", PollsView.as_view(), name="polls"),
    path("votes/", PollVotesView.as_view(), name="poll_votes"),
]
