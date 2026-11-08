from django.contrib import admin, messages
from django.utils import timezone

from nlp_engine.model_loader import ModelUnavailableError

from . import services
from .models import (
    FAQ,
    AlternativeQuestion,
    InformationType,
    KnowledgeArticle,
    KnowledgeCategory,
    PublicationStatus,
    VerificationStatus,
)


@admin.register(KnowledgeCategory)
class KnowledgeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "intent", "updated_at")
    search_fields = ("name", "description")
    list_filter = ("intent",)
    prepopulated_fields = {"slug": ("name",)}


class AlternativeQuestionInline(admin.TabularInline):
    model = AlternativeQuestion
    extra = 2
    fields = ("question_text", "embedding_ready", "updated_at")
    readonly_fields = ("embedding_ready", "updated_at")

    @admin.display(boolean=True, description="Embedding")
    def embedding_ready(self, obj):
        return obj.embedding is not None if obj.pk else None


class KnowledgeStatusActionsMixin:
    """Bulk publication and verification actions shared by FAQs and articles."""

    actions = ["publish", "unpublish", "archive", "mark_verified", "mark_unverified", "regenerate_embeddings"]

    def _bulk_update(self, request, queryset, message, **fields):
        count = queryset.update(updated_at=timezone.now(), **fields)
        services.invalidate_indexes()
        self.message_user(request, message.format(count=count), messages.SUCCESS)

    @admin.action(description="Publish selected records")
    def publish(self, request, queryset):
        self._bulk_update(request, queryset, "{count} record(s) published.",
                          publication_status=PublicationStatus.PUBLISHED)

    @admin.action(description="Unpublish selected records (set to draft)")
    def unpublish(self, request, queryset):
        self._bulk_update(request, queryset, "{count} record(s) unpublished.",
                          publication_status=PublicationStatus.DRAFT)

    @admin.action(description="Archive selected records")
    def archive(self, request, queryset):
        self._bulk_update(request, queryset, "{count} record(s) archived.",
                          publication_status=PublicationStatus.ARCHIVED)

    @admin.action(description="Mark as verified institutional information")
    def mark_verified(self, request, queryset):
        demonstration = queryset.filter(information_type=InformationType.DEMONSTRATION).count()
        if demonstration:
            self.message_user(
                request,
                f"{demonstration} selected record(s) are hypothetical demonstration information and cannot be "
                "verified. Change their information type to institutional after confirming the facts.",
                messages.ERROR,
            )
            return
        self._bulk_update(request, queryset, "{count} record(s) marked as verified.",
                          verification_status=VerificationStatus.VERIFIED)

    @admin.action(description="Mark as unverified")
    def mark_unverified(self, request, queryset):
        self._bulk_update(request, queryset, "{count} record(s) marked as unverified.",
                          verification_status=VerificationStatus.UNVERIFIED)

    @admin.action(description="Regenerate embeddings")
    def regenerate_embeddings(self, request, queryset):
        try:
            total = 0
            for record in queryset:
                if isinstance(record, FAQ):
                    total += services.refresh_faq_embeddings(record, force=True)
                else:
                    total += services.refresh_article_embedding(record, force=True)
        except ModelUnavailableError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return
        self.message_user(request, f"{total} embedding(s) regenerated.", messages.SUCCESS)


@admin.register(FAQ)
class FAQAdmin(KnowledgeStatusActionsMixin, admin.ModelAdmin):
    list_display = ("reference_code", "question", "category", "information_type", "verification_status",
                    "publication_status", "embedding_ready", "updated_at")
    list_filter = ("category", "information_type", "verification_status", "publication_status")
    search_fields = ("reference_code", "question", "answer", "alternative_questions__question_text")
    list_select_related = ("category",)
    inlines = [AlternativeQuestionInline]
    readonly_fields = ("embedding_ready", "embedding_model", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("reference_code", "category", "question", "answer", "keywords")}),
        ("Source and status", {"fields": ("source_description", "source_url", "information_type",
                                          "verification_status", "publication_status")}),
        ("System", {"classes": ("collapse",),
                    "fields": ("embedding_ready", "embedding_model", "created_at", "updated_at")}),
    )

    @admin.display(boolean=True, description="Embedding")
    def embedding_ready(self, obj):
        return obj.question_embedding is not None

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Ensure the question and every alternative (including inline edits) have fresh embeddings.
        try:
            services.refresh_faq_embeddings(form.instance)
        except ModelUnavailableError as exc:
            self.message_user(request, f"Saved, but embeddings could not be generated yet: {exc}", messages.WARNING)


@admin.register(AlternativeQuestion)
class AlternativeQuestionAdmin(admin.ModelAdmin):
    list_display = ("question_text", "faq", "embedding_ready", "updated_at")
    search_fields = ("question_text", "faq__question", "faq__reference_code")
    list_select_related = ("faq",)
    autocomplete_fields = ("faq",)

    @admin.display(boolean=True, description="Embedding")
    def embedding_ready(self, obj):
        return obj.embedding is not None


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(KnowledgeStatusActionsMixin, admin.ModelAdmin):
    list_display = ("reference_code", "title", "category", "information_type", "verification_status",
                    "publication_status", "updated_at")
    list_filter = ("category", "information_type", "verification_status", "publication_status")
    search_fields = ("reference_code", "title", "content")
    readonly_fields = ("embedding_model", "created_at", "updated_at")
