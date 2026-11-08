from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.exceptions import ServiceUnavailable
from nlp_engine.model_loader import ModelUnavailableError
from nlp_engine.preprocessing import PreprocessingError

from . import guest
from .access import owned_conversations
from .models import Conversation
from .serializers import (
    ChatResponseSerializer,
    ConversationSerializer,
    MessageCreateSerializer,
    MessageSerializer,
    build_chat_response,
)
from .services import get_chat_service

GUEST_HEADER = OpenApiParameter(
    "X-Guest-Token", str, location=OpenApiParameter.HEADER, required=False,
    description="Secret guest session token returned when a guest creates a conversation. "
                "Not needed for authenticated users.",
)


@extend_schema_view(
    list=extend_schema(parameters=[GUEST_HEADER]),
    retrieve=extend_schema(parameters=[GUEST_HEADER]),
    partial_update=extend_schema(parameters=[GUEST_HEADER]),
    destroy=extend_schema(parameters=[GUEST_HEADER]),
)
@extend_schema(tags=["chat"])
class ConversationViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Conversations for authenticated users and guests.

    Guests: the first `POST /api/chat/conversations/` returns a `guest_token`.
    Send it in the `X-Guest-Token` header on every later request.
    """

    serializer_class = ConversationSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = owned_conversations(self.request).annotate(message_count=Count("messages"))
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-updated_at", "-id")

    def get_throttles(self):
        if self.action == "messages" and self.request.method == "POST":
            self.throttle_scope = "chat_message"
            return [*super().get_throttles(), ScopedRateThrottle()]
        return super().get_throttles()

    @extend_schema(parameters=[GUEST_HEADER], responses={201: ConversationSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issued_token = None
        if request.user.is_authenticated:
            conversation = serializer.save(user=request.user)
        else:
            token = guest.get_guest_token(request)
            if token is None:
                token = issued_token = guest.generate_guest_token()
            conversation = serializer.save(guest_session_id=guest.hash_guest_token(token))
        conversation.message_count = 0
        data = dict(self.get_serializer(conversation).data)
        if issued_token:
            data["guest_token"] = issued_token
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        methods=["GET"], parameters=[GUEST_HEADER], responses={200: MessageSerializer(many=True)},
        summary="List the messages of a conversation",
    )
    @extend_schema(
        methods=["POST"], parameters=[GUEST_HEADER], request=MessageCreateSerializer,
        responses={201: ChatResponseSerializer}, summary="Ask the chatbot a question",
    )
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        if request.method == "GET":
            page = self.paginate_queryset(conversation.messages.order_by("created_at", "id"))
            return self.get_paginated_response(MessageSerializer(page, many=True).data)

        if conversation.status == Conversation.Status.ARCHIVED:
            raise ValidationError({"conversation": ["This conversation is archived. Start a new conversation."]})
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = get_chat_service().process_message(conversation, serializer.validated_data["content"])
        except PreprocessingError as exc:
            raise ValidationError({"content": [str(exc)]}, code=exc.code)
        except ModelUnavailableError as exc:
            raise ServiceUnavailable(
                "The chatbot's language model is not available on the server. " + str(exc)
            )
        return Response(build_chat_response(conversation, result), status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[GUEST_HEADER], request=None, responses={200: dict},
                   summary="Attach guest conversations to the logged-in account")
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def claim(self, request):
        """Move conversations from the guest session in `X-Guest-Token` to the authenticated user."""
        if not request.user.is_authenticated:
            raise NotAuthenticated()
        session_id = guest.get_guest_session_id(request)
        if not session_id:
            raise ValidationError({"X-Guest-Token": ["A valid guest token header is required."]})
        claimed = Conversation.objects.filter(user__isnull=True, guest_session_id=session_id).update(
            user=request.user, guest_session_id=None
        )
        return Response({"success": True, "claimed_conversations": claimed})
