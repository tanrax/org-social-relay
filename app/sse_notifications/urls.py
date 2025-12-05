from django.urls import path
from .views import SSENotificationsView

urlpatterns = [
    path("notifications/", SSENotificationsView.as_view(), name="sse-notifications"),
]
