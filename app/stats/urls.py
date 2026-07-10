from django.urls import path
from .views import StatsView

app_name = "stats"

urlpatterns = [
    path("", StatsView.as_view(), name="stats"),
]
