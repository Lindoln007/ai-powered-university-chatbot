from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                             related_name="conversations")
    # SHA-256 hash of the guest's secret session token (the raw token is never stored).
    guest_session_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    title = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "-updated_at"], name="conversation_user_recent_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(user__isnull=False) | Q(guest_session_id__isnull=False),
                name="conversation_has_owner",
            ),
        ]

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    def __str__(self):
        return self.title or f"Conversation {self.pk}"


class Message(models.Model):
    class SenderType(models.TextChoices):
        USER = "user", "User"
        BOT = "bot", "Chatbot"

    class ResponseType(models.TextChoices):
        ANSWER = "answer", "Answer"
        CLARIFICATION = "clarification", "Clarification request"
        FALLBACK = "fallback", "Fallback (no answer found)"
        SMALL_TALK = "small_talk", "Small talk"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender_type = models.CharField(max_length=8, choices=SenderType.choices)
    content = models.TextField()
    detected_intent = models.CharField(max_length=64, blank=True)
    intent_confidence = models.FloatField(null=True, blank=True)
    similarity_score = models.FloatField(null=True, blank=True)
    retrieved_faq = models.ForeignKey("knowledge_base.FAQ", null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="messages")
    response_type = models.CharField(max_length=16, choices=ResponseType.choices, blank=True)
    answered = models.BooleanField(null=True, blank=True)
    information_type = models.CharField(max_length=16, blank=True)
    # Sources, disclaimer, suggestions and ranking diagnostics for bot messages.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"], name="message_conversation_time_idx")]

    @property
    def timestamp(self):
        return self.created_at

    def __str__(self):
        return f"{self.sender_type}: {self.content[:60]}"
