from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nlp_engine.model_loader import model_status


class HealthView(APIView):
    """Reports whether the database is reachable and whether the NLP model is loaded."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: dict}, tags=["system"])
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            database_ok = True
        except Exception:  # pragma: no cover - only when the database is down
            database_ok = False
        return Response(
            {
                "success": database_ok,
                "database": "ok" if database_ok else "unavailable",
                "nlp_model": model_status(),
                "demo_mode": settings.CHATBOT_DEMO_MODE,
            },
            status=200 if database_ok else 503,
        )
