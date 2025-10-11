from django.urls import path
from .views import NotificationsView

urlpatterns = [
    path("", NotificationsView.as_view(), name="notifications"),
]
