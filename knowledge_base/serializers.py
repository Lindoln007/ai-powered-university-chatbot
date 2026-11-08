from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from .models import FAQ, AlternativeQuestion, KnowledgeArticle, KnowledgeCategory


def _run_model_clean(serializer, model, attrs):
    """Run the model's own validation (e.g. demonstration info cannot be verified)."""
    instance = serializer.instance or model()
    fields = {key: value for key, value in attrs.items() if key not in ("alternative_questions",)}
    for key, value in fields.items():
        setattr(instance, key, value)
    try:
        instance.clean()
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.message_dict)


class KnowledgeCategorySerializer(serializers.ModelSerializer):
    faq_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = KnowledgeCategory
        fields = ["id", "name", "slug", "description", "intent", "faq_count", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"slug": {"required": False}}


class AlternativeQuestionSerializer(serializers.ModelSerializer):
    has_embedding = serializers.SerializerMethodField()

    class Meta:
        model = AlternativeQuestion
        fields = ["id", "faq", "question_text", "has_embedding", "created_at", "updated_at"]
        read_only_fields = ["id", "has_embedding", "created_at", "updated_at"]

    def get_has_embedding(self, obj) -> bool:
        return obj.embedding is not None

    def validate_question_text(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("The alternative question cannot be empty.")
        return value


class FAQSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    alternative_questions = serializers.ListField(
        child=serializers.CharField(max_length=500), required=False, write_only=True,
        help_text="Full list of alternative formulations. On update, replaces the existing list.",
    )
    alternatives = serializers.SerializerMethodField()
    has_embedding = serializers.SerializerMethodField()
    is_demonstration = serializers.SerializerMethodField()

    class Meta:
        model = FAQ
        fields = [
            "id", "reference_code", "question", "answer", "category", "category_name", "keywords",
            "alternative_questions", "alternatives", "source_description", "source_url",
            "verification_status", "publication_status", "information_type", "is_demonstration",
            "has_embedding", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"reference_code": {"required": False}}

    def get_alternatives(self, obj) -> list[dict]:
        return [{"id": alt.id, "question_text": alt.question_text} for alt in obj.alternative_questions.all()]

    def get_has_embedding(self, obj) -> bool:
        return obj.question_embedding is not None

    def get_is_demonstration(self, obj) -> bool:
        return obj.information_type == "demonstration"

    def validate_keywords(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("Keywords must be a list of strings.")
        return [item.strip() for item in value if item.strip()]

    def validate_alternative_questions(self, value):
        cleaned, seen = [], set()
        for text in value:
            text = " ".join(text.split())
            if text and text.lower() not in seen:
                seen.add(text.lower())
                cleaned.append(text)
        return cleaned

    def validate(self, attrs):
        _run_model_clean(self, FAQ, attrs)
        return attrs

    @staticmethod
    def _sync_alternatives(faq, texts):
        existing = {alt.question_text: alt for alt in faq.alternative_questions.all()}
        for text, alternative in existing.items():
            if text not in texts:
                alternative.delete()
        for text in texts:
            if text not in existing:
                AlternativeQuestion.objects.create(faq=faq, question_text=text)

    @transaction.atomic
    def create(self, validated_data):
        alternatives = validated_data.pop("alternative_questions", [])
        faq = super().create(validated_data)
        self._sync_alternatives(faq, alternatives)
        return faq

    @transaction.atomic
    def update(self, instance, validated_data):
        alternatives = validated_data.pop("alternative_questions", None)
        faq = super().update(instance, validated_data)
        if alternatives is not None:
            self._sync_alternatives(faq, alternatives)
        return faq


class KnowledgeArticleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    source = serializers.CharField(source="source_description", required=False, allow_blank=True)
    has_embedding = serializers.SerializerMethodField()
    is_demonstration = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeArticle
        fields = [
            "id", "reference_code", "title", "content", "category", "category_name", "source", "source_url",
            "verification_status", "publication_status", "information_type", "is_demonstration",
            "has_embedding", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"reference_code": {"required": False}}

    def get_has_embedding(self, obj) -> bool:
        return obj.embedding is not None

    def get_is_demonstration(self, obj) -> bool:
        return obj.information_type == "demonstration"

    def validate(self, attrs):
        _run_model_clean(self, KnowledgeArticle, attrs)
        return attrs


class KnowledgeSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=500, help_text="Natural language search query.")
    type = serializers.ChoiceField(choices=["all", "faq", "article"], default="all")
    limit = serializers.IntegerField(min_value=1, max_value=20, default=5)
