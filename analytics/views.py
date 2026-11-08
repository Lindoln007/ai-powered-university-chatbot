from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdministrator

from . import services
from .models import QueryAnalytics
from .serializers import DateRangeQuerySerializer, UnansweredQuestionSerializer


class AnalyticsView(APIView):
    """Base class: administrator-only, with optional start_date / end_date filtering."""

    permission_classes = [IsAdministrator]

    def compute(self, date_range: services.DateRange, limit: int) -> dict:
        raise NotImplementedError

    @extend_schema(parameters=[DateRangeQuerySerializer], responses={200: dict}, tags=["analytics"])
    def get(self, request):
        params = DateRangeQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        date_range = services.DateRange(params.validated_data.get("start_date"), params.validated_data.get("end_date"))
        return Response({"success": True, **self.compute(date_range, params.validated_data["limit"])})


class OverviewView(AnalyticsView):
    def compute(self, date_range, limit):
        return services.overview(date_range)


class PopularQuestionsView(AnalyticsView):
    def compute(self, date_range, limit):
        return services.popular_questions(date_range, limit)


class CategoryStatisticsView(AnalyticsView):
    def compute(self, date_range, limit):
        return services.category_statistics(date_range)


class ResponsePerformanceView(AnalyticsView):
    def compute(self, date_range, limit):
        return services.response_performance(date_range)


class UsageView(AnalyticsView):
    def compute(self, date_range, limit):
        return services.usage(date_range)


class UnansweredSummaryView(AnalyticsView):
    """Unanswered questions grouped by wording, most frequent first (pending review only)."""

    def compute(self, date_range, limit):
        return {"date_range": date_range.as_dict(), "groups": services.unanswered_summary(date_range, limit)}


@extend_schema(
    tags=["analytics"],
    parameters=[OpenApiParameter("review_status", str, enum=["pending", "resolved", "dismissed"]),
                OpenApiParameter("start_date", str), OpenApiParameter("end_date", str)],
)
class UnansweredQuestionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                                viewsets.GenericViewSet):
    """Unanswered questions (knowledge gaps). Administrators can mark them resolved or dismissed."""

    serializer_class = UnansweredQuestionSerializer
    permission_classes = [IsAdministrator]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        queryset = QueryAnalytics.objects.filter(response_type=QueryAnalytics.ResponseType.FALLBACK)
        params = DateRangeQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        queryset = services.DateRange(params.validated_data.get("start_date"),
                                      params.validated_data.get("end_date")).filter(queryset, "timestamp")
        review_status = self.request.query_params.get("review_status")
        if review_status:
            queryset = queryset.filter(review_status=review_status)
        return queryset.order_by("-timestamp")
