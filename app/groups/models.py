from django.db import models
from app.feeds.models import Profile, Post


class Group(models.Model):
    """
    Represents a group/community in Org Social Relay
    """

    name = models.CharField(
        max_length=100, unique=True, help_text="Group name (no spaces)"
    )
    title = models.CharField(max_length=200, help_text="Display title of the group")
    description = models.TextField(help_text="Description of the group")
    avatar = models.URLField(blank=True, help_text="Group avatar URL")
    created_by = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="created_groups"
    )
    is_public = models.BooleanField(
        default=True, help_text="Whether the group is publicly accessible"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"Group: {self.name}"


class GroupMembership(models.Model):
    """
    Represents membership of profiles in groups
    """

    ROLE_CHOICES = [
        ("member", "Member"),
        ("moderator", "Moderator"),
        ("admin", "Admin"),
    ]

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="memberships"
    )
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="group_memberships"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "profile"]
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.profile.nick} in {self.group.name} ({self.role})"


class GroupPost(models.Model):
    """
    Represents posts shared in groups
    """

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="group_posts"
    )
    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name="shared_in_groups"
    )
    shared_by = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="shared_posts"
    )
    shared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["group", "post"]
        ordering = ["-shared_at"]

    def __str__(self):
        return f"Post by {self.post.profile.nick} shared in {self.group.name}"


class GroupInvitation(models.Model):
    """
    Represents invitations to join groups
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("expired", "Expired"),
    ]

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="invitations"
    )
    invited_profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="group_invitations"
    )
    invited_by = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="sent_group_invitations"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    message = models.TextField(blank=True, help_text="Optional invitation message")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["group", "invited_profile"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invitation for {self.invited_profile.nick} to join {self.group.name}"
