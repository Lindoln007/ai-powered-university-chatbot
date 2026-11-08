from django.contrib import admin

from .models import QueryAnalytics


@admin.register(QueryAnalytics)
class QueryAnalyticsAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "short_question", "detected_intent", "response_type", "similarity_score",
                    "retrieved_faq", "response_time_ms", "review_status")
    list_filter = ("response_type", "review_status", "detected_intent", "answered", "timestamp")
    search_fields = ("original_question", "normalized_question", "admin_notes")
    readonly_fields = ("original_question", "normalized_question", "conversation", "message", "detected_intent",
                       "intent_confidence", "retrieved_faq", "category", "similarity_score", "answered",
                       "response_type", "used_context", "response_time_ms", "timestamp")
    fields = readonly_fields + ("review_status", "resolved_faq", "admin_notes")
    actions = ["mark_resolved", "mark_dismissed"]
    list_select_related = ("retrieved_faq",)

    @admin.display(description="Question")
    def short_question(self, obj):
        return obj.original_question[:80]

    @admin.action(description="Mark selected unanswered questions as resolved")
    def mark_resolved(self, request, queryset):
        queryset.filter(response_type="fallback").update(review_status=QueryAnalytics.ReviewStatus.RESOLVED)

    @admin.action(description="Dismiss selected unanswered questions (out of scope)")
    def mark_dismissed(self, request, queryset):
        queryset.filter(response_type="fallback").update(review_status=QueryAnalytics.ReviewStatus.DISMISSED)

    def has_add_permission(self, request):
        return False
