import json
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings

from core.testing import DATASET_PATH, KnowledgeBaseTestBase
from nlp_engine import embeddings

from . import services
from .importer import import_dataset
from .models import FAQ, AlternativeQuestion, KnowledgeArticle, KnowledgeCategory


class DatasetImportTests(KnowledgeBaseTestBase):
    def test_dataset_is_imported_with_embeddings(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        self.assertEqual(FAQ.objects.count(), len(data["faqs"]))
        self.assertEqual(KnowledgeCategory.objects.count(), 12)
        self.assertGreaterEqual(FAQ.objects.count(), 45)
        self.assertGreater(AlternativeQuestion.objects.count(), FAQ.objects.count() * 2)
        self.assertFalse(FAQ.objects.filter(question_embedding__isnull=True).exists())
        self.assertFalse(AlternativeQuestion.objects.filter(embedding__isnull=True).exists())
        self.assertEqual(len(self.faq("ADM-002").question_embedding), 384)

    def test_all_imported_records_are_labelled_as_demonstration(self):
        self.assertFalse(FAQ.objects.exclude(information_type="demonstration").exists())
        self.assertFalse(FAQ.objects.filter(verification_status="verified").exists())

    def test_import_is_repeatable_without_duplicates(self):
        counts = (FAQ.objects.count(), AlternativeQuestion.objects.count(), KnowledgeArticle.objects.count())
        summary = import_dataset(DATASET_PATH)
        self.assertEqual(summary.faqs_created, 0)
        self.assertEqual(summary.alternatives_created, 0)
        self.assertEqual(summary.embeddings, {"faqs": 0, "alternatives": 0, "articles": 0})
        self.assertEqual(counts, (FAQ.objects.count(), AlternativeQuestion.objects.count(),
                                  KnowledgeArticle.objects.count()))

    def _write(self, payload) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, handle)
        handle.close()
        return Path(handle.name)

    def test_invalid_records_are_rejected_and_nothing_is_imported(self):
        path = self._write({"faqs": [
            {"reference_code": "BAD-1", "category": "does-not-exist", "question": "Q?", "answer": "A",
             "verification_status": "unverified", "publication_status": "published",
             "information_type": "demonstration"},
            {"reference_code": "BAD-2", "category": "admissions", "question": "", "answer": "A",
             "verification_status": "verified", "publication_status": "published",
             "information_type": "demonstration"},
        ]})
        before = FAQ.objects.count()
        summary = import_dataset(path)
        joined = " ".join(summary.errors)
        self.assertIn("unknown category", joined)
        self.assertIn("'question' is required", joined)
        self.assertIn("cannot be marked as verified", joined)
        self.assertEqual(FAQ.objects.count(), before)

    def test_import_updates_changed_records(self):
        data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        data["faqs"][0]["answer"] = "Updated demonstration answer."
        data["faqs"][0]["alternative_questions"] = data["faqs"][0]["alternative_questions"][:1] + ["A brand new way to ask"]
        summary = import_dataset(self._write(data))
        self.assertEqual(summary.faqs_updated, 1)
        self.assertEqual(summary.alternatives_created, 1)
        faq = self.faq(data["faqs"][0]["reference_code"])
        self.assertEqual(faq.answer, "Updated demonstration answer.")
        self.assertEqual(faq.alternative_questions.count(), 2)
        self.assertIsNotNone(faq.alternative_questions.get(question_text="A brand new way to ask").embedding)

    def test_management_command_runs(self):
        call_command("import_faqs", str(DATASET_PATH), stdout=open(tempfile.mktemp(), "w"))


class EmbeddingSynchronisationTests(KnowledgeBaseTestBase):
    def test_updating_question_refreshes_embedding(self):
        faq = self.faq("LIB-001")
        old_vector, old_hash = faq.question_embedding, faq.embedding_hash
        faq.question = "Is there a computer laboratory for students?"
        faq.save()
        faq.refresh_from_db()
        self.assertNotEqual(faq.embedding_hash, old_hash)
        self.assertFalse(np.allclose(old_vector, faq.question_embedding))
        np.testing.assert_allclose(faq.question_embedding, embeddings.encode_one(faq.question), atol=1e-5)

    def test_saving_without_text_change_does_not_re_encode(self):
        faq = self.faq("LIB-002")
        faq.answer = "A different answer"
        with mock.patch.object(embeddings, "encode", wraps=embeddings.encode) as encode:
            faq.save()
        encode.assert_not_called()

    def test_new_and_edited_alternatives_get_embeddings(self):
        faq = self.faq("LIB-001")
        alternative = AlternativeQuestion.objects.create(faq=faq, question_text="Can I read books on campus?")
        alternative.refresh_from_db()
        self.assertEqual(len(alternative.embedding), 384)
        old_hash = alternative.embedding_hash
        alternative.question_text = "Can I study quietly in the library?"
        alternative.save()
        alternative.refresh_from_db()
        self.assertNotEqual(alternative.embedding_hash, old_hash)

    def test_new_alternative_is_used_by_search_immediately(self):
        faq = self.faq("ACC-004")
        query = embeddings.encode_one("Do you have a list of landlords who rent to students?")
        AlternativeQuestion.objects.create(faq=faq, question_text="Do you have a list of landlords who rent to students?")
        hits = services.search_faqs(query)
        self.assertEqual(hits[0].key, faq.pk)
        self.assertAlmostEqual(hits[0].score, 1.0, places=3)

    def test_archived_and_deleted_faqs_are_not_retrieved(self):
        query = embeddings.encode_one("How do I borrow books from the library?")
        faq = self.faq("LIB-003")
        self.assertEqual(services.search_faqs(query)[0].key, faq.pk)
        faq.publication_status = "archived"
        faq.save()
        self.assertNotIn(faq.pk, [hit.key for hit in services.search_faqs(query)])
        faq.publication_status = "published"
        faq.save()
        self.assertEqual(services.search_faqs(query)[0].key, faq.pk)
        faq.delete()
        self.assertNotIn(faq.pk, [hit.key for hit in services.search_faqs(query)])

    def test_rebuild_embeddings_command(self):
        FAQ.objects.filter(reference_code="CAL-001").update(question_embedding=None, embedding_hash="")
        call_command("rebuild_embeddings", stdout=open(tempfile.mktemp(), "w"))
        self.assertIsNotNone(self.faq("CAL-001").question_embedding)


class VerificationFilteringTests(KnowledgeBaseTestBase):
    def setUp(self):
        super().setUp()
        self.verified = FAQ.objects.create(
            reference_code="OFF-001", category=KnowledgeCategory.objects.get(slug="contact-information"),
            question="What is the official verified test contact channel?", answer="Verified test answer.",
            information_type="institutional", verification_status="verified", publication_status="published",
        )

    def test_demonstration_information_cannot_be_verified(self):
        faq = self.faq("ADM-001")
        faq.verification_status = "verified"
        with self.assertRaises(ValidationError):
            faq.full_clean()

    def test_demo_mode_includes_labelled_demonstration_records(self):
        self.assertTrue(self.faq("ADM-001").is_retrievable(demo_mode=True))
        self.assertTrue(self.verified.is_retrievable(demo_mode=True))

    def test_official_mode_only_uses_verified_institutional_records(self):
        self.assertFalse(self.faq("ADM-001").is_retrievable(demo_mode=False))
        self.assertTrue(self.verified.is_retrievable(demo_mode=False))
        self.assertEqual(list(FAQ.objects.retrievable(demo_mode=False)), [self.verified])
        index = services.get_faq_index(demo_mode=False)
        self.assertEqual({entry.key for entry in index.entries}, {self.verified.pk})

    def test_draft_records_are_never_used(self):
        self.verified.verification_status = "draft"
        self.verified.save()
        self.assertFalse(self.verified.is_retrievable(demo_mode=True))
        self.assertFalse(self.verified.is_retrievable(demo_mode=False))


class KnowledgeAPITests(KnowledgeBaseTestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_user("admin1", role="administrator")
        self.category = KnowledgeCategory.objects.get(slug="library-services")

    def test_public_can_read_published_faqs(self):
        FAQ.objects.filter(reference_code="LIB-004").update(publication_status="draft")
        response = self.client.get("/api/knowledge/faqs/", {"page_size": 100})
        self.assertEqual(response.status_code, 200)
        codes = [item["reference_code"] for item in response.data["results"]]
        self.assertIn("LIB-001", codes)
        self.assertNotIn("LIB-004", codes)
        self.assertTrue(all(item["is_demonstration"] for item in response.data["results"]))
        self.assertEqual(self.client.get(f"/api/knowledge/faqs/{self.faq('LIB-004').pk}/").status_code, 404)

    def test_faq_filters_and_search(self):
        response = self.client.get("/api/knowledge/faqs/", {"category": "library-services"})
        self.assertEqual(response.data["count"], 4)
        response = self.client.get("/api/knowledge/faqs/", {"search": "hostel"})
        self.assertTrue(all(item["category_name"] == "Accommodation" for item in response.data["results"]))

    def test_categories_and_articles_are_listed(self):
        self.assertEqual(self.client.get("/api/knowledge/categories/").data["count"], 12)
        articles = self.client.get("/api/knowledge/articles/")
        self.assertEqual(articles.data["count"], 3)
        detail = self.client.get(f"/api/knowledge/articles/{articles.data['results'][0]['id']}/")
        self.assertEqual(detail.status_code, 200)

    def test_non_administrators_cannot_modify_knowledge(self):
        payload = {"question": "Q?", "answer": "A", "category": self.category.pk}
        self.assertEqual(self.client.post("/api/knowledge/faqs/", payload, format="json").status_code, 401)
        self.authenticate(self.make_user("student9"))
        self.assertEqual(self.client.post("/api/knowledge/faqs/", payload, format="json").status_code, 403)
        faq_id = self.faq("LIB-001").pk
        self.assertEqual(self.client.delete(f"/api/knowledge/faqs/{faq_id}/").status_code, 403)
        self.assertEqual(self.client.get("/api/knowledge/alternative-questions/").status_code, 403)

    def test_administrator_crud_with_automatic_embeddings(self):
        self.authenticate(self.admin)
        response = self.client.post("/api/knowledge/faqs/", {
            "question": "Can I print documents in the library?",
            "answer": "Demonstration answer about printing.",
            "category": self.category.pk,
            "keywords": ["printing"],
            "alternative_questions": ["Is there a printer for students?", "Where can I photocopy notes?"],
            "verification_status": "unverified",
            "publication_status": "published",
            "information_type": "demonstration",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        faq = FAQ.objects.get(pk=response.data["id"])
        self.assertTrue(faq.reference_code.startswith("FAQ-"))
        self.assertIsNotNone(faq.question_embedding)
        self.assertEqual(faq.alternative_questions.filter(embedding__isnull=False).count(), 2)

        hits = services.search_faqs(embeddings.encode_one("Where is the printer?"))
        self.assertEqual(hits[0].key, faq.pk)

        response = self.client.patch(f"/api/knowledge/faqs/{faq.pk}/", {
            "question": "Can I make photocopies in the library?",
            "alternative_questions": ["Is there a photocopier?"],
        }, format="json")
        self.assertEqual(response.status_code, 200)
        faq.refresh_from_db()
        np.testing.assert_allclose(faq.question_embedding, embeddings.encode_one(faq.question), atol=1e-5)
        self.assertEqual(list(faq.alternative_questions.values_list("question_text", flat=True)),
                         ["Is there a photocopier?"])

        response = self.client.post(f"/api/knowledge/faqs/{faq.pk}/archive/")
        self.assertEqual(response.data["publication_status"], "archived")
        self.assertEqual(self.client.delete(f"/api/knowledge/faqs/{faq.pk}/").status_code, 204)
        self.assertFalse(FAQ.objects.filter(pk=faq.pk).exists())

    def test_administrator_cannot_verify_demonstration_information(self):
        self.authenticate(self.admin)
        response = self.client.patch(f"/api/knowledge/faqs/{self.faq('LIB-001').pk}/",
                                     {"verification_status": "verified"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "validation_error")

    def test_administrator_manages_categories_articles_and_alternatives(self):
        self.authenticate(self.admin)
        category = self.client.post("/api/knowledge/categories/", {"name": "ICT Services"}, format="json")
        self.assertEqual(category.status_code, 201)
        self.assertEqual(category.data["slug"], "ict-services")
        article = self.client.post("/api/knowledge/articles/", {
            "title": "Wi-Fi guide", "content": "Demonstration Wi-Fi guide.", "category": category.data["id"],
            "publication_status": "published", "verification_status": "unverified",
        }, format="json")
        self.assertEqual(article.status_code, 201, article.data)
        self.assertTrue(KnowledgeArticle.objects.get(pk=article.data["id"]).embedding)
        self.assertEqual(self.client.delete(f"/api/knowledge/categories/{category.data['id']}/").status_code, 409)
        alternative = self.client.post("/api/knowledge/alternative-questions/", {
            "faq": self.faq("LIB-001").pk, "question_text": "Does the campus have a reading room?"}, format="json")
        self.assertEqual(alternative.status_code, 201)
        self.assertTrue(alternative.data["has_embedding"])
        listing = self.client.get("/api/knowledge/faqs/", {"publication_status": "published", "page_size": 1})
        self.assertEqual(listing.status_code, 200)

    def test_semantic_search_endpoint(self):
        response = self.client.get("/api/knowledge/search/", {"q": "Which courses can I study?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], self.faq("PROG-001").pk)
        self.assertEqual(response.data["results"][0]["information_type"], "demonstration")
        articles = self.client.get("/api/knowledge/search/", {"q": "steps to apply for admission", "type": "article"})
        self.assertEqual(articles.data["results"][0]["type"], "article")
        self.assertEqual(self.client.get("/api/knowledge/search/", {"q": "   "}).status_code, 400)
        self.assertEqual(self.client.get("/api/knowledge/search/").status_code, 400)

    @override_settings(CHATBOT_DEMO_MODE=False)
    def test_public_listing_in_official_mode_hides_demonstration_records(self):
        response = self.client.get("/api/knowledge/faqs/")
        self.assertEqual(response.data["count"], 0)
