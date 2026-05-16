from django.urls import path

from app.profile.views import ProfileView

urlpatterns = [
    path("", ProfileView.as_view(), name="profile"),
]
