from chat.models import Conversation, Message
from core.testing import KnowledgeBaseTestBase

from .models import ChatbotFeedback


class FeedbackTests(KnowledgeBaseTestBase):
    def setUp(self):
        super().setUp()
        self.conversation_id, self.headers = self.new_guest_conversation()
        response = self.ask(self.conversation_id, "Does the university have library services?", self.headers)
        self.bot_message_id = response.data["bot_response"]["id"]
        self.user_message_id = response.data["user_message"]["id"]

    def submit(self, message_id, rating=5, headers=None, **extra):
        return self.client.post("/api/feedback/", {"message": message_id, "rating": rating, **extra}, format="json",
                                headers=headers if headers is not None else self.headers)

    def test_owner_can_rate_a_bot_response(self):
        response = self.submit(self.bot_message_id, 5, comment="Very helpful")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["sentiment"], "positive")
        self.assertEqual(ChatbotFeedback.objects.get().comment, "Very helpful")

    def test_feedback_validation(self):
        self.assertEqual(self.submit(self.user_message_id).status_code, 400)
        self.assertEqual(self.submit(self.bot_message_id, rating=6).status_code, 400)
        self.assertEqual(self.submit(self.bot_message_id, rating=0).status_code, 400)
        self.assertEqual(self.submit(999999).status_code, 400)
        self.assertEqual(self.submit(self.bot_message_id, 1).status_code, 201)
        duplicate = self.submit(self.bot_message_id, 2)
        self.assertEqual(duplicate.status_code, 400)

    def test_cannot_rate_someone_elses_message(self):
        other = Conversation.objects.create(user=self.make_user("frank"))
        message = Message.objects.create(conversation=other, sender_type="bot", content="x")
        self.assertEqual(self.submit(message.pk).status_code, 400)
        self.assertEqual(self.submit(self.bot_message_id, headers={}).status_code, 400)

    def test_feedback_listing_is_restricted_to_administrators(self):
        self.submit(self.bot_message_id, 1, comment="Not useful")
        self.assertEqual(self.client.get("/api/feedback/").status_code, 401)
        self.authenticate(self.make_user("gina"))
        self.assertEqual(self.client.get("/api/feedback/").status_code, 403)
        self.authenticate(self.make_user("boss", role="administrator"))
        response = self.client.get("/api/feedback/", {"sentiment": "negative"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertEqual(item["question"], "Does the university have library services?")
        self.assertEqual(item["sentiment"], "negative")
        self.assertEqual(self.client.get("/api/feedback/", {"sentiment": "positive"}).data["count"], 0)
