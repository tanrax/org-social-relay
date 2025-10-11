from django.urls import path
from .views import RepliesToView

urlpatterns = [
    path("", RepliesToView.as_view(), name="replies-to"),
]
