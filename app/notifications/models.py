from django.db import models
from app.feeds.models import Profile, Post


class Mention(models.Model):
    """
    Represents a mention of a profile in a post
    """

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="mentions")
    mentioned_profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="mentions_received"
    )
    mentioned_nickname = models.CharField(
        max_length=100, help_text="Nickname used in the mention"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["post", "mentioned_profile"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.post.profile.nick} mentioned {self.mentioned_profile.nick}"


class Reply(models.Model):
    """
    Represents a reply relationship between posts
    """

    reply_post = models.OneToOneField(
        Post, on_delete=models.CASCADE, related_name="reply_info"
    )
    original_post_url = models.URLField(help_text="URL of the original post")
    original_post_id = models.CharField(
        max_length=50, help_text="ID of the original post"
    )
    original_profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="replies_received",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reply_post.profile.nick} replied to {self.original_post_url}#{self.original_post_id}"


class Notification(models.Model):
    """
    General notification model for mentions and replies
    """

    NOTIFICATION_TYPES = [
        ("mention", "Mention"),
        ("reply", "Reply"),
        ("poll_vote", "Poll Vote"),
    ]

    recipient = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name="generated_notifications"
    )
    mention = models.ForeignKey(
        Mention, on_delete=models.CASCADE, null=True, blank=True
    )
    reply = models.ForeignKey(Reply, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type} notification for {self.recipient.nick}"
