from django.contrib import admin

from .models import ChatbotFeedback


@admin.register(ChatbotFeedback)
class ChatbotFeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "rating", "sentiment", "user", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("comment", "message__content")
    readonly_fields = ("message", "user", "rating", "comment", "created_at")
