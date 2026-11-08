from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("categories", views.KnowledgeCategoryViewSet, basename="category")
router.register("faqs", views.FAQViewSet, basename="faq")
router.register("alternative-questions", views.AlternativeQuestionViewSet, basename="alternative-question")
router.register("articles", views.KnowledgeArticleViewSet, basename="article")

urlpatterns = [
    path("search/", views.KnowledgeSearchView.as_view(), name="knowledge-search"),
    path("", include(router.urls)),
]
