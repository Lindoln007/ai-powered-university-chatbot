from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ChatbotFeedback(models.Model):
    """A user's rating of a single chatbot response (1 = very poor ... 5 = very helpful)."""

    POSITIVE_MIN_RATING = 4
    NEGATIVE_MAX_RATING = 2

    message = models.OneToOneField("chat.Message", on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="chatbot_feedback")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "chatbot feedback"
        verbose_name_plural = "chatbot feedback"
        constraints = [
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="feedback_rating_range"),
        ]

    @property
    def sentiment(self) -> str:
        if self.rating >= self.POSITIVE_MIN_RATING:
            return "positive"
        if self.rating <= self.NEGATIVE_MAX_RATING:
            return "negative"
        return "neutral"

    def __str__(self):
        return f"Feedback {self.rating}/5 on message {self.message_id}"
