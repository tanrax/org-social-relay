from django.urls import path
from .views import ReactionsView

urlpatterns = [
    path("", ReactionsView.as_view(), name="reactions"),
]
