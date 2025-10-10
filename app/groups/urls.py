from django.urls import path
from .views import GroupsView, GroupMessagesView

urlpatterns = [
    path("", GroupsView.as_view(), name="groups-list"),
    path("<str:group_slug>/", GroupMessagesView.as_view(), name="group-messages"),
]
