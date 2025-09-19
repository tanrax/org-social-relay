from django.db import models


class Profile(models.Model):
    """
    Represents an Org Social profile (social.org file)
    """

    feed = models.URLField(unique=True, help_text="URL to the social.org file")
    title = models.CharField(max_length=200, help_text="Title of the social feed")
    nick = models.CharField(max_length=100, help_text="Nickname (no spaces allowed)")
    description = models.TextField(
        blank=True, help_text="Short description about the profile"
    )
    avatar = models.URLField(
        blank=True, help_text="URL to avatar image (128x128px JPG/PNG)"
    )
    version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Version identifier for tracking changes (hash of content)",
    )
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_updated"]

    def __str__(self):
        return f"{self.nick} ({self.feed})"


class ProfileLink(models.Model):
    """
    Links associated with a profile (LINK field in social.org)
    """

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="links")
    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["profile", "url"]


class ProfileContact(models.Model):
    """
    Contact information for a profile (CONTACT field in social.org)
    """

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="contacts"
    )
    contact_type = models.CharField(
        max_length=50, help_text="Type of contact (email, xmpp, matrix, etc.)"
    )
    contact_value = models.CharField(max_length=200, help_text="Contact information")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["profile", "contact_type", "contact_value"]


class Follow(models.Model):
    """
    Represents a follow relationship between profiles
    """

    follower = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="following"
    )
    followed = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="followers"
    )
    nickname = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional nickname for the followed profile",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["follower", "followed"]

    def __str__(self):
        return f"{self.follower.nick} follows {self.followed.nick}"


class Post(models.Model):
    """
    Represents a post in Org Social
    """

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="posts")
    post_id = models.CharField(
        max_length=50, help_text="Unique timestamp identifier (RFC 3339 format)"
    )
    content = models.TextField(help_text="Post content")

    # Optional properties
    language = models.CharField(
        max_length=10, blank=True, help_text="Language code (LANG property)"
    )
    tags = models.CharField(
        max_length=500, blank=True, help_text="Space-separated tags"
    )
    client = models.CharField(
        max_length=100, blank=True, help_text="Client application used"
    )
    reply_to = models.CharField(
        max_length=300,
        blank=True,
        help_text="ID of post being replied to (URL#ID format)",
    )
    mood = models.CharField(
        max_length=10, blank=True, help_text="Mood indicator (emoji)"
    )

    # Poll related fields
    poll_end = models.DateTimeField(
        blank=True, null=True, help_text="End time for polls"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["profile", "post_id"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.profile.nick}: {self.content[:50]}..."

    @property
    def is_poll(self):
        return self.poll_end is not None

    @property
    def is_reply(self):
        return bool(self.reply_to)


class PollOption(models.Model):
    """
    Options for a poll post
    """

    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name="poll_options"
    )
    option_text = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        unique_together = ["post", "option_text"]

    def __str__(self):
        return f"{self.post.profile.nick} poll: {self.option_text}"


class PollVote(models.Model):
    """
    Represents a vote on a poll
    """

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="poll_votes")
    poll_post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="votes_received",
        help_text="The original poll post",
    )
    poll_option = models.CharField(max_length=200, help_text="Selected poll option")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["post", "poll_post"]

    def __str__(self):
        return f"{self.post.profile.nick} voted {self.poll_option}"


class Mention(models.Model):
    """
    Represents a mention in a post
    """

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="mentions")
    mentioned_profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="incoming_mentions",
        help_text="The profile that was mentioned",
    )
    nickname = models.CharField(
        max_length=100, blank=True, help_text="Nickname used in the mention"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["post", "mentioned_profile"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.post.profile.nick} mentioned {self.mentioned_profile.nick}"


class Feed(models.Model):
    """
    Represents a feed URL
    """

    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.url
