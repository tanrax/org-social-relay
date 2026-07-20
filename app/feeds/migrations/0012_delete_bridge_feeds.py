from django.db import migrations
from django.db.models import Q


def delete_bridge_feeds(apps, schema_editor):
    """
    Bridge virtual feeds are a connection helper, not real accounts.
    Remove any that were registered before they were excluded from
    registration and discovery.
    """
    Feed = apps.get_model("feeds", "Feed")
    Feed.objects.filter(
        Q(url__contains="/bridge/activitypub/") | Q(url__contains="/bridge/rss/")
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("feeds", "0011_outgoingwebmention"),
    ]

    operations = [
        migrations.RunPython(delete_bridge_feeds, migrations.RunPython.noop),
    ]
