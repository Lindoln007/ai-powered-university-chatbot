from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    can_delete = False
    fields = ("created_at", "sender_type", "content", "detected_intent", "similarity_score", "response_type",
              "retrieved_faq")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "is_guest", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "user__username", "user__email")
    readonly_fields = ("user", "guest_session_id", "created_at", "updated_at")
    inlines = [MessageInline]

    @admin.display(boolean=True)
    def is_guest(self, obj):
        return obj.is_guest


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender_type", "short_content", "detected_intent", "similarity_score",
                    "response_type", "created_at")
    list_filter = ("sender_type", "response_type", "detected_intent", "created_at")
    search_fields = ("content",)
    readonly_fields = [field.name for field in Message._meta.fields]

    @admin.display(description="Content")
    def short_content(self, obj):
        return obj.content[:80]

    def has_add_permission(self, request):
        return False
