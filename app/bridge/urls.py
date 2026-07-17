from django.urls import path, re_path

from .views import (
    ActivityPubBridgeFeedView,
    ActivityPubBridgeListView,
    BridgeIndexView,
    RssBridgeView,
)

urlpatterns = [
    path("", BridgeIndexView.as_view(), name="bridge-index"),
    path(
        "activitypub/",
        ActivityPubBridgeListView.as_view(),
        name="bridge-activitypub-list",
    ),
    re_path(
        r"^activitypub/(?P<handle>[^/]+)/$",
        ActivityPubBridgeFeedView.as_view(),
        name="bridge-activitypub-feed",
    ),
    path("rss/", RssBridgeView.as_view(), name="bridge-rss"),
]
