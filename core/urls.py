"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path, include
from app.public.views import root_view
from app.feeds.views import FeedsView

urlpatterns = [
    path("", root_view, name="root"),
    path("feeds/", FeedsView.as_view(), name="feeds"),
    path("feed-content/", include("app.feedcontent.urls")),
    path("mentions/", include("app.mentions.urls")),
    path("reactions/", include("app.reactions.urls")),
    path("replies-to/", include("app.repliesto.urls")),
    path("boosts/", include("app.boosts.urls")),
    path("interactions/", include("app.interactions.urls")),
    path("notifications/", include("app.notifications.urls")),
    path("replies/", include("app.replies.urls")),
    path("search/", include("app.search.urls")),
    path("groups/", include("app.groups.urls")),
    path("polls/", include("app.polls.urls")),
    path("rss.xml", include("app.rss.urls")),
]
