import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from core.models import TimeStampedModel
from nlp_engine.intent_classifier import Intent


class InformationType(models.TextChoices):
    INSTITUTIONAL = "institutional", "Institutional information"
    DEMONSTRATION = "demonstration", "Hypothetical demonstration information"


class VerificationStatus(models.TextChoices):
    VERIFIED = "verified", "Verified institutional information"
    UNVERIFIED = "unverified", "Unverified (demonstration or pending verification)"
    DRAFT = "draft", "Draft information"


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft (not published)"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


def retrievable_filter(demo_mode: bool | None = None) -> Q:
    """Which knowledge records the chatbot may use.

    * Official mode (demo mode off): only published, verified institutional information.
    * Demo mode: additionally published, unverified records (which are always labelled).
    Draft and archived records are never used.
    """
    if demo_mode is None:
        demo_mode = settings.CHATBOT_DEMO_MODE
    verified = Q(verification_status=VerificationStatus.VERIFIED, information_type=InformationType.INSTITUTIONAL)
    condition = Q(publication_status=PublicationStatus.PUBLISHED)
    if demo_mode:
        return condition & (verified | Q(verification_status=VerificationStatus.UNVERIFIED))
    return condition & verified


class KnowledgeQuerySet(models.QuerySet):
    def retrievable(self, demo_mode: bool | None = None):
        return self.filter(retrievable_filter(demo_mode))


class KnowledgeCategory(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    intent = models.CharField(
        max_length=64, choices=Intent.choices(), blank=True,
        help_text="Intent most closely associated with this category (used to break ties between close matches).",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "knowledge category"
        verbose_name_plural = "knowledge categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class KnowledgeRecord(TimeStampedModel):
    """Fields shared by FAQs and knowledge articles."""

    reference_code = models.CharField(
        max_length=32, unique=True, blank=True,
        help_text="Stable identifier used by the dataset import (generated automatically if left blank).",
    )
    category = models.ForeignKey(KnowledgeCategory, on_delete=models.PROTECT, related_name="%(class)ss")
    source_description = models.CharField(max_length=500, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    verification_status = models.CharField(
        max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.DRAFT, db_index=True
    )
    publication_status = models.CharField(
        max_length=16, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT, db_index=True
    )
    information_type = models.CharField(
        max_length=16, choices=InformationType.choices, default=InformationType.DEMONSTRATION, db_index=True
    )
    # Embedding bookkeeping (managed by knowledge_base.services, never edited by hand).
    embedding_hash = models.CharField(max_length=64, blank=True, editable=False)
    embedding_model = models.CharField(max_length=200, blank=True, editable=False)

    objects = KnowledgeQuerySet.as_manager()

    REFERENCE_PREFIX = "KB"

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if (self.information_type == InformationType.DEMONSTRATION
                and self.verification_status == VerificationStatus.VERIFIED):
            raise ValidationError({
                "verification_status": "Hypothetical demonstration information cannot be marked as verified "
                                       "institutional information. Change the information type first."
            })

    def save(self, *args, **kwargs):
        if not self.reference_code:
            self.reference_code = f"{self.REFERENCE_PREFIX}-{secrets.token_hex(4).upper()}"
        super().save(*args, **kwargs)

    def is_retrievable(self, demo_mode: bool | None = None) -> bool:
        return type(self).objects.retrievable(demo_mode).filter(pk=self.pk).exists()


class FAQ(KnowledgeRecord):
    question = models.CharField(max_length=500)
    answer = models.TextField()
    keywords = models.JSONField(default=list, blank=True, help_text="List of keywords, e.g. [\"fees\", \"tuition\"].")
    question_embedding = models.JSONField(null=True, blank=True, editable=False)

    REFERENCE_PREFIX = "FAQ"

    class Meta:
        ordering = ["reference_code"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"
        indexes = [
            models.Index(fields=["publication_status", "verification_status", "information_type"],
                         name="faq_retrievable_idx"),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.keywords, list) or not all(isinstance(k, str) for k in self.keywords):
            raise ValidationError({"keywords": "Keywords must be a list of text values."})

    @property
    def has_embedding(self) -> bool:
        return self.question_embedding is not None

    def __str__(self):
        return f"{self.reference_code}: {self.question}"


class AlternativeQuestion(TimeStampedModel):
    faq = models.ForeignKey(FAQ, on_delete=models.CASCADE, related_name="alternative_questions")
    question_text = models.CharField(max_length=500)
    embedding = models.JSONField(null=True, blank=True, editable=False)
    embedding_hash = models.CharField(max_length=64, blank=True, editable=False)
    embedding_model = models.CharField(max_length=200, blank=True, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["faq", "question_text"], name="unique_alternative_per_faq"),
        ]

    def __str__(self):
        return self.question_text


class KnowledgeArticle(KnowledgeRecord):
    title = models.CharField(max_length=255)
    content = models.TextField()
    embedding = models.JSONField(null=True, blank=True, editable=False)

    REFERENCE_PREFIX = "ART"

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["publication_status", "verification_status", "information_type"],
                         name="article_retrievable_idx"),
        ]

    @property
    def source(self) -> str:
        return self.source_description

    @property
    def embedding_text(self) -> str:
        return f"{self.title}. {self.content[:1000]}"

    def __str__(self):
        return self.title
