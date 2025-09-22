from django.urls import path
from .views import GroupsView, GroupMembersView, GroupMessagesView

urlpatterns = [
    path("", GroupsView.as_view(), name="groups-list"),
    path("<int:group_id>/", GroupMessagesView.as_view(), name="group-messages"),
    path("<int:group_id>/members/", GroupMembersView.as_view(), name="group-members"),
]