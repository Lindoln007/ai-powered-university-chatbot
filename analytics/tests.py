from datetime import timedelta

from django.utils import timezone

from chat.models import Conversation, Message
from core.testing import KnowledgeBaseTestBase
from feedback.models import ChatbotFeedback

from .models import QueryAnalytics


class AnalyticsTests(KnowledgeBaseTestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_user("admin", role="administrator")
        self.student = self.make_user("student")
        self.conversation_id, self.headers = self.new_guest_conversation()
        questions = [
            "How do I apply for admission?",
            "How can I join the university?",
            "Does the university have library services?",
            "How do I bake a chocolate cake?",
            "Hello",
        ]
        self.responses = [self.ask(self.conversation_id, q, self.headers).data["bot_response"] for q in questions]
        ChatbotFeedback.objects.create(message_id=self.responses[0]["id"], rating=5)
        ChatbotFeedback.objects.create(message_id=self.responses[2]["id"], rating=1)
        self.authenticate(self.admin)

    def test_analytics_require_administrator(self):
        endpoints = ["overview", "popular-questions", "unanswered-questions", "category-statistics",
                     "response-performance", "usage", "unanswered-questions/summary"]
        self.logout_client()
        for endpoint in endpoints:
            self.assertEqual(self.client.get(f"/api/analytics/{endpoint}/").status_code, 401, endpoint)
        self.authenticate(self.student)
        for endpoint in endpoints:
            self.assertEqual(self.client.get(f"/api/analytics/{endpoint}/").status_code, 403, endpoint)

    def test_overview_matches_database(self):
        data = self.client.get("/api/analytics/overview/").data
        self.assertEqual(data["total_registered_users"], 2)
        self.assertEqual(data["total_conversations"], Conversation.objects.count())
        self.assertEqual(data["total_messages"], Message.objects.count())
        self.assertEqual(data["total_messages"], 10)
        self.assertEqual(data["total_chatbot_questions"], 5)
        self.assertEqual(data["answered_questions"], 3)
        self.assertEqual(data["unanswered_questions"], 1)
        self.assertEqual(data["small_talk_messages"], 1)
        self.assertEqual(data["answer_rate"], 0.75)
        self.assertEqual(data["feedback"], {"total": 2, "positive": 1, "negative": 1, "neutral": 0,
                                            "average_rating": 3.0})
        expected_avg = sum(QueryAnalytics.objects.values_list("response_time_ms", flat=True)) / 5
        self.assertAlmostEqual(data["average_response_time_ms"], expected_avg, places=1)

    def test_popular_questions(self):
        data = self.client.get("/api/analytics/popular-questions/").data
        top = data["most_frequently_answered_faqs"][0]
        self.assertEqual(top["reference_code"], "ADM-001")
        self.assertEqual(top["times_asked"], 2)

    def test_category_statistics(self):
        data = self.client.get("/api/analytics/category-statistics/").data
        categories = {row["category"]: row for row in data["categories"]}
        self.assertEqual(categories["Admissions"]["answered_questions"], 2)
        self.assertEqual(categories["Admissions"]["positive_feedback"], 1)
        self.assertEqual(categories["Library Services"]["negative_feedback"], 1)
        intents = {row["detected_intent"]: row for row in data["intents"]}
        self.assertEqual(intents["admissions_enquiry"]["questions"], 2)

    def test_response_performance_and_usage(self):
        data = self.client.get("/api/analytics/response-performance/").data
        self.assertEqual(data["total_queries"], 5)
        self.assertGreater(data["average_response_time_ms"], 0)
        self.assertLessEqual(data["min_response_time_ms"], data["p95_response_time_ms"])
        self.assertEqual(sum(day["questions"] for day in data["daily"]), 5)
        self.assertEqual(data["monthly"][0]["questions"], 5)

    def test_date_filtering(self):
        future = (timezone.localdate() + timedelta(days=1)).isoformat()
        data = self.client.get("/api/analytics/overview/", {"start_date": future}).data
        self.assertEqual(data["total_chatbot_questions"], 0)
        today = timezone.localdate().isoformat()
        data = self.client.get("/api/analytics/overview/", {"start_date": today, "end_date": today}).data
        self.assertEqual(data["total_chatbot_questions"], 5)
        bad = self.client.get("/api/analytics/overview/", {"start_date": future, "end_date": today})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.get("/api/analytics/overview/", {"start_date": "yesterday"}).status_code, 400)

    def test_unanswered_question_management(self):
        listing = self.client.get("/api/analytics/unanswered-questions/", {"review_status": "pending"})
        self.assertEqual(listing.data["count"], 1)
        item = listing.data["results"][0]
        self.assertEqual(item["original_question"], "How do I bake a chocolate cake?")
        summary = self.client.get("/api/analytics/unanswered-questions/summary/").data
        self.assertEqual(summary["groups"][0]["times_asked"], 1)

        response = self.client.patch(f"/api/analytics/unanswered-questions/{item['id']}/",
                                     {"review_status": "dismissed", "admin_notes": "Out of scope"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/analytics/unanswered-questions/",
                                         {"review_status": "pending"}).data["count"], 0)
        invalid = self.client.patch(f"/api/analytics/unanswered-questions/{item['id']}/",
                                    {"review_status": "not_applicable"}, format="json")
        self.assertEqual(invalid.status_code, 400)
