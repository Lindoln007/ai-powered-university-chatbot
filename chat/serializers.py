from django.conf import settings
from rest_framework import serializers

from .models import Conversation, Message


class ConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True, required=False)
    is_guest = serializers.BooleanField(read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "status", "is_guest", "message_count", "created_at", "updated_at"]
        read_only_fields = ["id", "is_guest", "message_count", "created_at", "updated_at"]
        extra_kwargs = {"title": {"required": False, "allow_blank": True}}


class MessageSerializer(serializers.ModelSerializer):
    intent = serializers.CharField(source="detected_intent", read_only=True)
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)
    sources = serializers.SerializerMethodField()
    suggestions = serializers.SerializerMethodField()
    related_questions = serializers.SerializerMethodField()
    disclaimer = serializers.SerializerMethodField()
    is_verified = serializers.SerializerMethodField()
    used_context = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id", "conversation", "sender_type", "content", "intent", "intent_confidence", "similarity_score",
            "response_type", "answered", "information_type", "is_verified", "disclaimer", "retrieved_faq",
            "sources", "suggestions", "related_questions", "used_context", "timestamp",
        ]
        read_only_fields = fields

    def get_sources(self, obj) -> list:
        return obj.metadata.get("sources", [])

    def get_suggestions(self, obj) -> list:
        return obj.metadata.get("suggestions", [])

    def get_related_questions(self, obj) -> list:
        return obj.metadata.get("related", [])

    def get_disclaimer(self, obj) -> str | None:
        return obj.metadata.get("disclaimer")

    def get_is_verified(self, obj) -> bool | None:
        return obj.metadata.get("is_verified")

    def get_used_context(self, obj) -> bool:
        return bool(obj.metadata.get("used_context"))


class MessageCreateSerializer(serializers.Serializer):
    content = serializers.CharField(
        max_length=settings.CHATBOT_MAX_QUESTION_LENGTH,
        trim_whitespace=True,
        help_text="The user's natural language question.",
    )


class BotResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    content = serializers.CharField()
    intent = serializers.CharField()
    intent_confidence = serializers.FloatField(allow_null=True)
    similarity_score = serializers.FloatField(allow_null=True)
    answered = serializers.BooleanField()
    response_type = serializers.CharField()
    information_type = serializers.CharField(allow_null=True)
    verification_status = serializers.CharField(allow_null=True)
    is_verified = serializers.BooleanField(allow_null=True)
    disclaimer = serializers.CharField(allow_null=True)
    sources = serializers.ListField(child=serializers.DictField())
    suggestions = serializers.ListField(child=serializers.DictField())
    related_questions = serializers.ListField(child=serializers.DictField())
    matched_question = serializers.CharField(allow_null=True)
    used_context = serializers.BooleanField()
    response_time_ms = serializers.FloatField()
    timestamp = serializers.DateTimeField()


class ChatResponseSerializer(serializers.Serializer):
    """Documentation-only serializer describing the message submission response."""

    success = serializers.BooleanField()
    conversation_id = serializers.IntegerField()
    user_message = serializers.DictField()
    bot_response = BotResponseSerializer()


def build_chat_response(conversation, result) -> dict:
    bot = result.bot_message
    meta = bot.metadata
    return {
        "success": True,
        "conversation_id": conversation.pk,
        "user_message": {
            "id": result.user_message.pk,
            "content": result.user_message.content,
            "timestamp": result.user_message.created_at,
        },
        "bot_response": {
            "id": bot.pk,
            "content": bot.content,
            "intent": bot.detected_intent,
            "intent_confidence": bot.intent_confidence,
            "similarity_score": bot.similarity_score,
            "answered": bot.answered,
            "response_type": bot.response_type,
            "information_type": bot.information_type or None,
            "verification_status": meta.get("verification_status"),
            "is_verified": meta.get("is_verified"),
            "disclaimer": meta.get("disclaimer"),
            "sources": meta.get("sources", []),
            "suggestions": meta.get("suggestions", []),
            "related_questions": meta.get("related", []),
            "matched_question": meta.get("matched_question"),
            "used_context": meta.get("used_context", False),
            "response_time_ms": result.response_time_ms,
            "timestamp": bot.created_at,
        },
    }
