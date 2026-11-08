from django.conf import settings
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdministrator, IsAdministratorOrReadOnly, is_administrator
from core.exceptions import ServiceUnavailable
from nlp_engine import embeddings
from nlp_engine.model_loader import ModelUnavailableError
from nlp_engine.preprocessing import PreprocessingError, preprocess

from . import services
from .models import FAQ, AlternativeQuestion, KnowledgeArticle, KnowledgeCategory, PublicationStatus
from .serializers import (
    AlternativeQuestionSerializer,
    FAQSerializer,
    KnowledgeArticleSerializer,
    KnowledgeCategorySerializer,
    KnowledgeSearchQuerySerializer,
)

ADMIN_FILTER_PARAMETERS = [
    OpenApiParameter("category", int, description="Filter by category id."),
    OpenApiParameter("verification_status", str, description="Administrators only: verified, unverified, draft."),
    OpenApiParameter("publication_status", str, description="Administrators only: draft, published, archived."),
    OpenApiParameter("information_type", str, description="institutional or demonstration."),
    OpenApiParameter("search", str, description="Case-insensitive text search."),
]


class RefreshAfterSaveMixin:
    """Embeddings are written by signals after save; reload so responses report them."""

    def perform_create(self, serializer):
        serializer.save()
        serializer.instance.refresh_from_db()

    def perform_update(self, serializer):
        serializer.save()
        serializer.instance.refresh_from_db()


class KnowledgeFilterMixin:
    """Public users only see records the chatbot may use; administrators see everything."""

    search_fields: tuple = ()

    def filter_knowledge(self, queryset):
        params = self.request.query_params
        if not is_administrator(self.request.user):
            queryset = queryset.retrievable()
        else:
            for field in ("verification_status", "publication_status"):
                if params.get(field):
                    queryset = queryset.filter(**{field: params[field]})
        if params.get("information_type"):
            queryset = queryset.filter(information_type=params["information_type"])
        if params.get("category"):
            category = params["category"]
            queryset = queryset.filter(category_id=category) if category.isdigit() else queryset.filter(
                category__slug=category)
        if params.get("search"):
            condition = Q()
            for field in self.search_fields:
                condition |= Q(**{f"{field}__icontains": params["search"]})
            queryset = queryset.filter(condition).distinct()
        return queryset


@extend_schema(tags=["knowledge"])
class KnowledgeCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeCategorySerializer
    permission_classes = [IsAdministratorOrReadOnly]

    def get_queryset(self):
        return KnowledgeCategory.objects.annotate(
            faq_count=Count("faqs", filter=Q(faqs__publication_status=PublicationStatus.PUBLISHED))
        ).order_by("name")

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.faqs.exists() or category.knowledgearticles.exists():
            return Response(
                {"success": False, "error": {"code": "category_in_use",
                                             "message": "Move or delete the category's FAQs and articles first."}},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(list=extend_schema(parameters=ADMIN_FILTER_PARAMETERS))
@extend_schema(tags=["knowledge"])
class FAQViewSet(RefreshAfterSaveMixin, KnowledgeFilterMixin, viewsets.ModelViewSet):
    serializer_class = FAQSerializer
    permission_classes = [IsAdministratorOrReadOnly]
    search_fields = ("question", "answer", "alternative_questions__question_text", "reference_code")

    def get_queryset(self):
        queryset = FAQ.objects.select_related("category").prefetch_related("alternative_questions")
        return self.filter_knowledge(queryset).order_by("reference_code")

    @extend_schema(request=None, responses={200: FAQSerializer})
    @action(detail=True, methods=["post"], permission_classes=[IsAdministrator])
    def archive(self, request, pk=None):
        """Archive an FAQ so the chatbot no longer uses it (keeps it for reference)."""
        faq = self.get_object()
        faq.publication_status = PublicationStatus.ARCHIVED
        faq.save(update_fields=["publication_status", "updated_at"])
        return Response(self.get_serializer(faq).data)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="regenerate-embeddings", permission_classes=[IsAdministrator])
    def regenerate_embeddings(self, request, pk=None):
        faq = self.get_object()
        try:
            count = services.refresh_faq_embeddings(faq, force=True)
        except ModelUnavailableError as exc:
            raise ServiceUnavailable(str(exc))
        return Response({"success": True, "embeddings_regenerated": count})


@extend_schema(tags=["knowledge"])
class AlternativeQuestionViewSet(RefreshAfterSaveMixin, viewsets.ModelViewSet):
    """Administrator CRUD for alternative question formulations."""

    serializer_class = AlternativeQuestionSerializer
    permission_classes = [IsAdministrator]

    def get_queryset(self):
        queryset = AlternativeQuestion.objects.select_related("faq").order_by("faq_id", "id")
        faq = self.request.query_params.get("faq")
        return queryset.filter(faq_id=faq) if faq and faq.isdigit() else queryset


@extend_schema_view(list=extend_schema(parameters=ADMIN_FILTER_PARAMETERS))
@extend_schema(tags=["knowledge"])
class KnowledgeArticleViewSet(RefreshAfterSaveMixin, KnowledgeFilterMixin, viewsets.ModelViewSet):
    serializer_class = KnowledgeArticleSerializer
    permission_classes = [IsAdministratorOrReadOnly]
    search_fields = ("title", "content", "reference_code")

    def get_queryset(self):
        return self.filter_knowledge(KnowledgeArticle.objects.select_related("category")).order_by("title")


@extend_schema(tags=["knowledge"])
class KnowledgeSearchView(APIView):
    """Semantic search over the knowledge base (FAQs and articles) using sentence embeddings."""

    permission_classes = [AllowAny]

    @extend_schema(parameters=[KnowledgeSearchQuerySerializer], responses={200: dict})
    def get(self, request):
        params = KnowledgeSearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        try:
            processed = preprocess(params.validated_data["q"])
        except PreprocessingError as exc:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"q": [str(exc)]})
        try:
            query_vector = embeddings.encode_one(processed.cleaned)
            limit = params.validated_data["limit"]
            search_type = params.validated_data["type"]
            faq_hits = services.search_faqs(query_vector, limit) if search_type in ("all", "faq") else []
            article_hits = services.search_articles(query_vector, limit) if search_type in ("all", "article") else []
        except ModelUnavailableError as exc:
            raise ServiceUnavailable(str(exc))

        min_score = settings.KNOWLEDGE_SEARCH_MIN_SCORE
        faq_hits = [hit for hit in faq_hits if hit.score >= min_score]
        article_hits = [hit for hit in article_hits if hit.score >= min_score]
        faqs = services.load_faqs([hit.key for hit in faq_hits])
        articles = KnowledgeArticle.objects.select_related("category").in_bulk([hit.key for hit in article_hits])

        results = []
        for hit in faq_hits:
            faq = faqs.get(hit.key)
            if faq:
                results.append({
                    "type": "faq", "id": faq.pk, "title": faq.question, "content": faq.answer,
                    "category": faq.category.name, "score": round(hit.score, 4), "matched_text": hit.matched_text,
                    "information_type": faq.information_type, "verification_status": faq.verification_status,
                })
        for hit in article_hits:
            article = articles.get(hit.key)
            if article:
                results.append({
                    "type": "article", "id": article.pk, "title": article.title, "content": article.content,
                    "category": article.category.name, "score": round(hit.score, 4), "matched_text": hit.matched_text,
                    "information_type": article.information_type,
                    "verification_status": article.verification_status,
                })
        results.sort(key=lambda item: -item["score"])
        return Response({
            "success": True,
            "query": processed.cleaned,
            "demo_mode": settings.CHATBOT_DEMO_MODE,
            "count": len(results),
            "results": results[: params.validated_data["limit"]],
        })
