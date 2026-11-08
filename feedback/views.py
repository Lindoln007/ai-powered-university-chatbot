from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from accounts.permissions import IsAdministrator
from chat.views import GUEST_HEADER

from .models import ChatbotFeedback
from .serializers import AdminChatbotFeedbackSerializer, ChatbotFeedbackSerializer


@extend_schema(tags=["feedback"])
class FeedbackView(generics.ListCreateAPIView):
    """POST: rate a chatbot response (owner of the conversation only). GET: administrators only."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAdministrator()]

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "feedback"
            return [*super().get_throttles(), ScopedRateThrottle()]
        return super().get_throttles()

    def get_serializer_class(self):
        return ChatbotFeedbackSerializer if self.request.method == "POST" else AdminChatbotFeedbackSerializer

    def get_queryset(self):
        queryset = ChatbotFeedback.objects.select_related("message", "user").order_by("-created_at")
        sentiment = self.request.query_params.get("sentiment")
        if sentiment == "positive":
            queryset = queryset.filter(rating__gte=ChatbotFeedback.POSITIVE_MIN_RATING)
        elif sentiment == "negative":
            queryset = queryset.filter(rating__lte=ChatbotFeedback.NEGATIVE_MAX_RATING)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)

    @extend_schema(parameters=[OpenApiParameter("sentiment", str, enum=["positive", "negative"])])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(parameters=[GUEST_HEADER])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
