from rest_framework import serializers

from knowledge_base.models import FAQ

from .models import QueryAnalytics


class DateRangeQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False, help_text="Inclusive start date (YYYY-MM-DD).")
    end_date = serializers.DateField(required=False, help_text="Inclusive end date (YYYY-MM-DD).")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=10)

    def validate(self, attrs):
        if attrs.get("start_date") and attrs.get("end_date") and attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError({"end_date": "end_date must be on or after start_date."})
        return attrs


class UnansweredQuestionSerializer(serializers.ModelSerializer):
    resolved_faq = serializers.PrimaryKeyRelatedField(queryset=FAQ.objects.all(), required=False, allow_null=True)

    class Meta:
        model = QueryAnalytics
        fields = [
            "id", "original_question", "normalized_question", "detected_intent", "similarity_score",
            "conversation", "review_status", "resolved_faq", "admin_notes", "timestamp",
        ]
        read_only_fields = [
            "id", "original_question", "normalized_question", "detected_intent", "similarity_score",
            "conversation", "timestamp",
        ]

    def validate_review_status(self, value):
        if value == QueryAnalytics.ReviewStatus.NOT_APPLICABLE:
            raise serializers.ValidationError("Use pending, resolved or dismissed for unanswered questions.")
        return value
