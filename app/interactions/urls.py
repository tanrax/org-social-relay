from django.urls import path
from .views import InteractionsView

app_name = "interactions"

urlpatterns = [
    path("", InteractionsView.as_view(), name="interactions"),
]
