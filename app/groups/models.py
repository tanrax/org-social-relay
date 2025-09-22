from django.db import models
from app.feeds.models import Profile


class GroupMember(models.Model):
    """
    Tracks which feeds are members of which groups.
    Groups themselves are configured via GROUPS environment variable.
    """
    group_name = models.CharField(max_length=100, db_index=True)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='group_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['group_name', 'profile']
        ordering = ['-joined_at']
        indexes = [
            models.Index(fields=['group_name', '-joined_at']),
        ]

    def __str__(self):
        return f"{self.profile.feed} in {self.group_name}"
