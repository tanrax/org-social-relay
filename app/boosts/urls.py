from django.urls import path
from .views import BoostsView

app_name = "boosts"

urlpatterns = [
    path("", BoostsView.as_view(), name="boosts"),
]
