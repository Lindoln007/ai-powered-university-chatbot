from unittest import mock

from django.test import override_settings
from rest_framework.throttling import SimpleRateThrottle

from analytics.models import QueryAnalytics
from core.testing import KnowledgeBaseTestBase
from knowledge_base.models import FAQ, KnowledgeCategory
from nlp_engine.model_loader import ModelUnavailableError

from .models import Conversation, Message


class SemanticRetrievalTests(KnowledgeBaseTestBase):
    """Differently worded questions must retrieve the same stored answer."""

    def setUp(self):
        super().setUp()
        self.conversation_id, self.headers = self.new_guest_conversation()

    def assert_retrieves(self, question, code):
        response = self.ask(self.conversation_id, question, self.headers)
        self.assertEqual(response.status_code, 201, response.data)
        bot = response.data["bot_response"]
        self.assertEqual(bot["response_type"], "answer", f"{question!r}: {bot}")
        self.assertEqual(bot["sources"][0]["reference_code"], code, question)
        self.assertTrue(bot["answered"])
        return bot

    def test_programme_paraphrases_retrieve_the_same_answer(self):
        answers = set()
        for question in ["What programmes does the university offer?", "Which courses can I study?",
                         "What academic programmes are available?"]:
            with self.subTest(question=question):
                bot = self.assert_retrieves(question, "PROG-001")
                answers.add(bot["content"])
        self.assertEqual(len(answers), 1)

    def test_admission_requirement_paraphrases(self):
        for question in ["What are the admission requirements?", "What grades do I need to qualify?",
                         "What qualifications are required to join?"]:
            with self.subTest(question=question):
                self.assert_retrieves(question, "ADM-002")

    def test_held_out_paraphrases_from_other_categories(self):
        cases = {
            "How much will I pay per semester?": "FEE-001",
            "When will lectures begin this semester?": "CAL-002",
            "How long can I keep a library book?": "LIB-003",
            "I need someone to talk to about my problems": "SUP-002",
        }
        for question, code in cases.items():
            with self.subTest(question=question):
                self.assert_retrieves(question, code)

    def test_alternative_question_match_is_reported(self):
        bot = self.assert_retrieves("What do I need to join the university?", "ADM-002")
        self.assertEqual(bot["matched_question"], "What do I need to join the university?")
        self.assertAlmostEqual(bot["similarity_score"], 1.0, places=3)
        self.assertEqual(bot["intent"], "admissions_enquiry")

    def test_unrelated_questions_trigger_fallback(self):
        for question in ["How do I bake a chocolate cake?", "Who won the football world cup in 2018?",
                         "What is the capital city of Japan?", "Recommend a good movie to watch tonight"]:
            with self.subTest(question=question):
                bot = self.ask(self.conversation_id, question, self.headers).data["bot_response"]
                self.assertEqual(bot["response_type"], "fallback")
                self.assertFalse(bot["answered"])
                self.assertEqual(bot["sources"], [])
                self.assertIn("couldn't find verified information", bot["content"])
        self.assertEqual(QueryAnalytics.objects.filter(response_type="fallback", review_status="pending").count(), 4)

    @override_settings(CHATBOT_SIMILARITY_THRESHOLD=0.99, CHATBOT_HIGH_CONFIDENCE=0.995)
    def test_similarity_threshold_is_applied(self):
        bot = self.ask(self.conversation_id, "Which degree courses are offered by the university?",
                       self.headers).data["bot_response"]
        self.assertEqual(bot["response_type"], "fallback")
        self.assertLess(bot["similarity_score"], 0.99)

    def test_demonstration_information_is_labelled(self):
        bot = self.assert_retrieves("How do I apply for admission?", "ADM-001")
        self.assertEqual(bot["information_type"], "demonstration")
        self.assertFalse(bot["is_verified"])
        self.assertIn("hypothetical demonstration information", bot["disclaimer"])
        self.assertIn("[Demonstration information]", bot["content"])

    def test_answers_include_related_questions(self):
        response = self.ask(self.conversation_id, "How do I apply for a room in the hostel?", self.headers)
        related = response.data["bot_response"]["related_questions"]
        self.assertTrue(1 <= len(related) <= 3)
        answered_id = response.data["bot_response"]["sources"][0]["id"]
        self.assertNotIn(answered_id, [item["faq_id"] for item in related])
        self.assertIn("Accommodation", [item["category"] for item in related])
        history = self.client.get(f"/api/chat/conversations/{self.conversation_id}/messages/", headers=self.headers)
        self.assertEqual(history.data["results"][1]["related_questions"], related)
        fallback = self.ask(self.conversation_id, "How do I bake a chocolate cake?", self.headers)
        self.assertEqual(fallback.data["bot_response"]["related_questions"], [])

    def test_small_talk(self):
        bot = self.ask(self.conversation_id, "Hello!", self.headers).data["bot_response"]
        self.assertEqual(bot["response_type"], "small_talk")
        self.assertIsNone(bot["similarity_score"])

    @override_settings(CHATBOT_HIGH_CONFIDENCE=0.99, CHATBOT_CLARIFICATION_MARGIN=0.2)
    def test_ambiguous_question_requests_clarification(self):
        category = KnowledgeCategory.objects.get(slug="library-services")
        for code, question in [("TST-1", "When does the computer lab open?"),
                               ("TST-2", "What time does the computer lab open?")]:
            FAQ.objects.create(reference_code=code, category=category, question=question, answer="Demo.",
                               publication_status="published", verification_status="unverified")
        bot = self.ask(self.conversation_id, "computer lab opening time", self.headers).data["bot_response"]
        self.assertEqual(bot["response_type"], "clarification", bot)
        self.assertGreaterEqual(len(bot["suggestions"]), 2)
        self.assertFalse(bot["answered"])


class OfficialModeTests(KnowledgeBaseTestBase):
    @override_settings(CHATBOT_DEMO_MODE=False)
    def test_official_mode_never_returns_demonstration_information(self):
        conversation_id, headers = self.new_guest_conversation()
        bot = self.ask(conversation_id, "How do I apply for admission?", headers).data["bot_response"]
        self.assertEqual(bot["response_type"], "fallback")

        verified = FAQ.objects.create(
            reference_code="OFF-1", category=KnowledgeCategory.objects.get(slug="admissions"),
            question="How do I apply for admission?", answer="Verified institutional answer.",
            information_type="institutional", verification_status="verified", publication_status="published",
            source_description="Test source",
        )
        bot = self.ask(conversation_id, "How do I apply for admission?", headers).data["bot_response"]
        self.assertEqual(bot["response_type"], "answer")
        self.assertEqual(bot["sources"][0]["id"], verified.pk)
        self.assertTrue(bot["is_verified"])
        self.assertIsNone(bot["disclaimer"])
        self.assertEqual(bot["content"], "Verified institutional answer.")


class ConversationContextTests(KnowledgeBaseTestBase):
    def test_follow_up_about_fees_after_admissions(self):
        conversation_id, headers = self.new_guest_conversation()
        self.ask(conversation_id, "What programmes are available?", headers)
        self.ask(conversation_id, "What are the admission requirements?", headers)
        bot = self.ask(conversation_id, "What about the fees?", headers).data["bot_response"]
        self.assertEqual(bot["response_type"], "answer", bot)
        self.assertEqual(bot["sources"][0]["category"], "Tuition and Fees")
        self.assertEqual(bot["intent"], "fees_enquiry")

    def test_pronoun_follow_up_uses_previous_topic(self):
        conversation_id, headers = self.new_guest_conversation()
        self.ask(conversation_id, "How do I apply for a room in the hostel?", headers)
        bot = self.ask(conversation_id, "How much does it cost?", headers).data["bot_response"]
        self.assertEqual(bot["sources"][0]["reference_code"], "ACC-003")
        self.assertTrue(bot["used_context"])

    def test_context_is_not_used_for_unrelated_questions(self):
        conversation_id, headers = self.new_guest_conversation()
        self.ask(conversation_id, "How do I apply for admission?", headers)
        bot = self.ask(conversation_id, "What about the weather in Paris?", headers).data["bot_response"]
        self.assertEqual(bot["response_type"], "fallback")


class ConversationAPITests(KnowledgeBaseTestBase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user("alice")
        self.other = self.make_user("bob")

    def test_authenticated_conversation_lifecycle(self):
        self.authenticate(self.user)
        created = self.client.post("/api/chat/conversations/", {"title": "Admissions"}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertNotIn("guest_token", created.data)
        conversation_id = created.data["id"]

        response = self.ask(conversation_id, "How do I register for a semester?")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["conversation_id"], conversation_id)
        self.assertEqual(response.data["user_message"]["content"], "How do I register for a semester?")

        messages = self.client.get(f"/api/chat/conversations/{conversation_id}/messages/")
        self.assertEqual(messages.data["count"], 2)
        user_message, bot_message = messages.data["results"]
        self.assertEqual((user_message["sender_type"], bot_message["sender_type"]), ("user", "bot"))
        self.assertEqual(bot_message["retrieved_faq"], self.faq("REG-001").pk)
        self.assertIsNotNone(bot_message["similarity_score"])
        self.assertEqual(bot_message["intent"], "registration_enquiry")

        listing = self.client.get("/api/chat/conversations/")
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["message_count"], 2)

        renamed = self.client.patch(f"/api/chat/conversations/{conversation_id}/", {"title": "Registration"},
                                    format="json")
        self.assertEqual(renamed.data["title"], "Registration")
        self.assertEqual(self.client.put(f"/api/chat/conversations/{conversation_id}/", {}).status_code, 405)

        self.ask(conversation_id, "Can I register late?")
        self.assertEqual(Message.objects.filter(conversation_id=conversation_id).count(), 4)
        self.assertEqual(self.client.delete(f"/api/chat/conversations/{conversation_id}/").status_code, 204)
        self.assertFalse(Message.objects.filter(conversation_id=conversation_id).exists())

    def test_title_is_generated_from_first_question(self):
        self.authenticate(self.user)
        conversation_id = self.client.post("/api/chat/conversations/", {}, format="json").data["id"]
        self.ask(conversation_id, "Where can I access the academic calendar?")
        self.assertEqual(Conversation.objects.get(pk=conversation_id).title, "Where can I access the academic calendar?")

    def test_users_cannot_access_other_users_conversations(self):
        conversation = Conversation.objects.create(user=self.other, title="Private")
        self.authenticate(self.user)
        base = f"/api/chat/conversations/{conversation.pk}/"
        self.assertEqual(self.client.get(base).status_code, 404)
        self.assertEqual(self.client.get(base + "messages/").status_code, 404)
        self.assertEqual(self.ask(conversation.pk, "Hello").status_code, 404)
        self.assertEqual(self.client.patch(base, {"title": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(base).status_code, 404)
        self.assertEqual(self.client.get("/api/chat/conversations/").data["count"], 0)
        self.assertTrue(Conversation.objects.filter(pk=conversation.pk).exists())

    def test_guest_sessions_are_isolated(self):
        first_id, first_headers = self.new_guest_conversation()
        second_id, second_headers = self.new_guest_conversation()
        self.assertEqual(self.ask(first_id, "Is there a library?", first_headers).status_code, 201)
        self.assertEqual(self.ask(first_id, "Is there a library?", second_headers).status_code, 404)
        self.assertEqual(self.ask(first_id, "Is there a library?").status_code, 404)
        self.assertEqual(self.client.get("/api/chat/conversations/").data["count"], 0)
        listing = self.client.get("/api/chat/conversations/", headers=first_headers)
        self.assertEqual([item["id"] for item in listing.data["results"]], [first_id])
        # The raw token is never stored.
        stored = Conversation.objects.get(pk=first_id).guest_session_id
        self.assertNotEqual(stored, first_headers["X-Guest-Token"])
        self.assertEqual(len(stored), 64)

    def test_guest_can_reuse_token_for_new_conversations_and_claim_them(self):
        first_id, headers = self.new_guest_conversation()
        second = self.client.post("/api/chat/conversations/", {}, format="json", headers=headers)
        self.assertNotIn("guest_token", second.data)
        self.assertEqual(self.client.get("/api/chat/conversations/", headers=headers).data["count"], 2)
        self.authenticate(self.user)
        claimed = self.client.post("/api/chat/conversations/claim/", headers=headers)
        self.assertEqual(claimed.data["claimed_conversations"], 2)
        self.assertEqual(self.client.get("/api/chat/conversations/").data["count"], 2)

    def test_message_validation(self):
        conversation_id, headers = self.new_guest_conversation()
        for payload in [{}, {"content": ""}, {"content": "    "}, {"content": "?!?"},
                        {"content": "x" * 501}]:
            with self.subTest(payload=str(payload)[:30]):
                response = self.client.post(f"/api/chat/conversations/{conversation_id}/messages/", payload,
                                            format="json", headers=headers)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.data["success"])
        self.assertEqual(Message.objects.count(), 0)

    def test_archived_conversation_rejects_new_messages(self):
        conversation_id, headers = self.new_guest_conversation()
        self.client.patch(f"/api/chat/conversations/{conversation_id}/", {"status": "archived"}, format="json",
                          headers=headers)
        self.assertEqual(self.ask(conversation_id, "Is there a library?", headers).status_code, 400)

    def test_model_unavailable_returns_503_without_saving(self):
        conversation_id, headers = self.new_guest_conversation()
        with mock.patch("chat.services.embeddings.encode_one", side_effect=ModelUnavailableError("missing")):
            response = self.ask(conversation_id, "Is there a library?", headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Message.objects.count(), 0)

    def test_unexpected_errors_do_not_leak_internals(self):
        conversation_id, headers = self.new_guest_conversation()
        self.client.raise_request_exception = False
        with mock.patch("chat.services.ChatService.process_message",
                        side_effect=RuntimeError("psycopg secret table detail")), \
                self.assertLogs("core.exceptions", level="ERROR"):
            response = self.ask(conversation_id, "Is there a library?", headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "server_error")
        self.assertNotIn("psycopg", response.content.decode())

    def test_chat_messages_are_rate_limited(self):
        conversation_id, headers = self.new_guest_conversation()
        rates = {**SimpleRateThrottle.THROTTLE_RATES, "chat_message": "2/minute"}
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates):
            statuses = [self.ask(conversation_id, "Is there a library?", headers).status_code for _ in range(3)]
        self.assertEqual(statuses, [201, 201, 429])
