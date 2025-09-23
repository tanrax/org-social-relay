from django.urls import path
from .views import GroupsView, GroupMembersView, GroupMessagesView

urlpatterns = [
    path("", GroupsView.as_view(), name="groups-list"),
    path("<str:group_name>/", GroupMessagesView.as_view(), name="group-messages"),
    path("<str:group_name>/members/", GroupMembersView.as_view(), name="group-members"),
]
