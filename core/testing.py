"""Shared helpers for the automated test suite."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from knowledge_base import services as knowledge
from knowledge_base.importer import import_dataset
from knowledge_base.models import FAQ

DATASET_PATH = settings.BASE_DIR / "data" / "university_faqs.json"
STRONG_PASSWORD = "Sunbird-Lake-2026!"


class APITestBase(APITestCase):
    """Clears throttle history between tests and offers user helpers."""

    def setUp(self):
        super().setUp()
        cache.clear()
        knowledge.invalidate_indexes()

    @staticmethod
    def make_user(username="student1", role="student", **extra):
        return get_user_model().objects.create_user(
            username=username, email=f"{username}@example.com", password=STRONG_PASSWORD, role=role, **extra
        )

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return token

    def logout_client(self):
        self.client.credentials()


class KnowledgeBaseTestBase(APITestBase):
    """Imports the real demonstration dataset (with real embeddings) once per test class."""

    @classmethod
    def setUpTestData(cls):
        summary = import_dataset(DATASET_PATH)
        assert not summary.errors, summary.errors

    @staticmethod
    def faq(code: str) -> FAQ:
        return FAQ.objects.get(reference_code=code)

    def ask(self, conversation_id, content, headers=None):
        return self.client.post(f"/api/chat/conversations/{conversation_id}/messages/", {"content": content},
                                format="json", headers=headers or {})

    def new_guest_conversation(self):
        response = self.client.post("/api/chat/conversations/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        return response.data["id"], {"X-Guest-Token": response.data["guest_token"]}
