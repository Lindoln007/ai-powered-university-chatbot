from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("unanswered-questions", views.UnansweredQuestionViewSet, basename="unanswered-question")

urlpatterns = [
    path("overview/", views.OverviewView.as_view(), name="analytics-overview"),
    path("popular-questions/", views.PopularQuestionsView.as_view(), name="analytics-popular-questions"),
    path("unanswered-questions/summary/", views.UnansweredSummaryView.as_view(), name="analytics-unanswered-summary"),
    path("category-statistics/", views.CategoryStatisticsView.as_view(), name="analytics-category-statistics"),
    path("response-performance/", views.ResponsePerformanceView.as_view(), name="analytics-response-performance"),
    path("usage/", views.UsageView.as_view(), name="analytics-usage"),
    path("", include(router.urls)),
]
