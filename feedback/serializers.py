from rest_framework import serializers

from chat.models import Message
from chat.access import owned_conversations

from .models import ChatbotFeedback


class ChatbotFeedbackSerializer(serializers.ModelSerializer):
    sentiment = serializers.CharField(read_only=True)
    message = serializers.PrimaryKeyRelatedField(queryset=Message.objects.all(),
                                                 help_text="Id of the chatbot message being rated.")

    class Meta:
        model = ChatbotFeedback
        fields = ["id", "message", "rating", "comment", "sentiment", "created_at"]
        read_only_fields = ["id", "sentiment", "created_at"]

    def validate_message(self, message):
        request = self.context["request"]
        if not owned_conversations(request).filter(pk=message.conversation_id).exists():
            # Do not reveal whether the message exists in someone else's conversation.
            raise serializers.ValidationError("Message not found.")
        if message.sender_type != Message.SenderType.BOT:
            raise serializers.ValidationError("Feedback can only be given on chatbot responses.")
        if ChatbotFeedback.objects.filter(message=message).exists():
            raise serializers.ValidationError("Feedback has already been submitted for this response.")
        return message


class AdminChatbotFeedbackSerializer(ChatbotFeedbackSerializer):
    question = serializers.SerializerMethodField()
    response = serializers.CharField(source="message.content", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True, default=None)

    class Meta(ChatbotFeedbackSerializer.Meta):
        fields = ChatbotFeedbackSerializer.Meta.fields + ["question", "response", "username"]

    def get_question(self, obj) -> str | None:
        previous = (Message.objects.filter(conversation_id=obj.message.conversation_id,
                                           sender_type=Message.SenderType.USER, created_at__lte=obj.message.created_at)
                    .order_by("-created_at", "-id").first())
        return previous.content if previous else None
