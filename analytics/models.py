from django.db import models


class QueryAnalytics(models.Model):
    """One row per question processed by the chatbot, used for analytics and gap analysis."""

    class ResponseType(models.TextChoices):
        ANSWER = "answer", "Answer"
        CLARIFICATION = "clarification", "Clarification request"
        FALLBACK = "fallback", "Fallback (unanswered)"
        SMALL_TALK = "small_talk", "Small talk"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        RESOLVED = "resolved", "Resolved (knowledge added)"
        DISMISSED = "dismissed", "Dismissed (out of scope)"
        NOT_APPLICABLE = "not_applicable", "Not applicable (answered)"

    original_question = models.TextField()
    normalized_question = models.TextField()
    conversation = models.ForeignKey("chat.Conversation", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="query_analytics")
    message = models.OneToOneField("chat.Message", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="query_analytics")
    detected_intent = models.CharField(max_length=64, db_index=True)
    intent_confidence = models.FloatField(null=True, blank=True)
    retrieved_faq = models.ForeignKey("knowledge_base.FAQ", null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="query_analytics")
    category = models.ForeignKey("knowledge_base.KnowledgeCategory", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="query_analytics")
    similarity_score = models.FloatField(null=True, blank=True)
    answered = models.BooleanField(default=False, db_index=True)
    response_type = models.CharField(max_length=16, choices=ResponseType.choices, db_index=True)
    used_context = models.BooleanField(default=False)
    response_time_ms = models.FloatField()
    review_status = models.CharField(max_length=16, choices=ReviewStatus.choices,
                                     default=ReviewStatus.NOT_APPLICABLE, db_index=True)
    resolved_faq = models.ForeignKey("knowledge_base.FAQ", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="resolved_queries",
                                     help_text="FAQ created or updated to answer this question.")
    admin_notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "query analytics record"
        verbose_name_plural = "query analytics"
        indexes = [models.Index(fields=["response_type", "timestamp"], name="analytics_type_time_idx")]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.response_type}: {self.original_question[:60]}"
