"""The chatbot processing pipeline.

    user question
      -> validation and preprocessing          (nlp_engine.preprocessing)
      -> sentence embedding                    (nlp_engine.embeddings, all-MiniLM-L6-v2)
      -> intent detection                      (nlp_engine.intent_classifier)
      -> semantic search over stored embeddings (knowledge_base.services / nlp_engine.semantic_search)
      -> threshold + ambiguity decision        (nlp_engine.semantic_search.decide)
      -> optional conversational context       (previous answered question, only as a fallback)
      -> grounded response                     (nlp_engine.response_generator)
      -> persistence of both messages + analytics
"""

import logging
import time
from dataclasses import dataclass

import numpy as np
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from analytics.services import record_query
from knowledge_base import services as knowledge
from nlp_engine import embeddings
from nlp_engine.intent_classifier import Intent, IntentResult, get_intent_classifier
from nlp_engine.preprocessing import detect_small_talk, looks_like_follow_up, preprocess
from nlp_engine.response_generator import GeneratedResponse, ResponseGenerator
from nlp_engine.semantic_search import RetrievalDecision, decide

from .models import Conversation, Message

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    user_message: Message
    bot_message: Message
    response: GeneratedResponse
    response_time_ms: float


@dataclass
class _Retrieval:
    decision: RetrievalDecision
    intent: IntentResult
    faqs: dict
    used_context: bool = False


class ChatService:
    def __init__(self):
        self.generator = ResponseGenerator(settings.CHATBOT_INSTITUTION_NAME)

    # -- retrieval -------------------------------------------------------
    def _retrieve(self, text: str) -> _Retrieval:
        vector = embeddings.encode_one(text)
        return self._rank(vector, get_intent_classifier().classify(vector))

    @staticmethod
    def _rank(vector, intent: IntentResult, exclude: set[int] = frozenset()) -> _Retrieval:
        hits = [hit for hit in knowledge.search_faqs(vector, settings.CHATBOT_TOP_K + len(exclude))
                if hit.key not in exclude]
        faqs = knowledge.load_faqs([hit.key for hit in hits])
        preferred = {key for key, faq in faqs.items() if intent.intent != Intent.UNKNOWN
                     and faq.category.intent == intent.intent}
        decision = decide(
            hits,
            threshold=settings.CHATBOT_SIMILARITY_THRESHOLD,
            clarification_margin=settings.CHATBOT_CLARIFICATION_MARGIN,
            high_confidence=settings.CHATBOT_HIGH_CONFIDENCE,
            preferred_keys=preferred,
        )
        return _Retrieval(decision, intent, faqs)

    @staticmethod
    def _previous_topic(conversation: Conversation):
        """The FAQ that answered the most recent successfully answered question, if any."""
        last_answer = (conversation.messages.filter(sender_type=Message.SenderType.BOT,
                                                    retrieved_faq__isnull=False,
                                                    response_type=Message.ResponseType.ANSWER)
                       .select_related("retrieved_faq").order_by("-created_at", "-id").first())
        return last_answer.retrieved_faq if last_answer else None

    def _retrieve_with_context(self, conversation: Conversation, text: str) -> _Retrieval:
        """Resolve short follow-ups ("What about the fees?", "How much does it cost?").

        The follow-up's embedding is blended with a smaller share of the previous
        topic's embedding, so the new wording stays dominant while ambiguous
        references are resolved towards the conversation topic. The previously
        answered FAQ is excluded (a follow-up asks for something new), and the
        result is still an exact knowledge base record that must pass the same
        similarity threshold, so context can never introduce unverified content.
        """
        vector = embeddings.encode_one(text)
        intent = get_intent_classifier().classify(vector)
        result = self._rank(vector, intent)
        if not looks_like_follow_up(text):
            return result
        best = result.decision.best
        if result.decision.outcome == "answer" and best.score >= settings.CHATBOT_HIGH_CONFIDENCE:
            return result
        previous = self._previous_topic(conversation)
        if previous is None or previous.question_embedding is None:
            return result

        blended = vector + settings.CHATBOT_CONTEXT_WEIGHT * embeddings.from_storage(previous.question_embedding)
        blended /= np.linalg.norm(blended)
        if intent.intent == Intent.UNKNOWN:
            intent = get_intent_classifier().classify(blended)
        contextual = self._rank(blended, intent, exclude={previous.pk})
        if contextual.decision.outcome != "answer":
            return result
        if result.decision.outcome == "answer" and contextual.decision.best.score <= best.score:
            return result
        contextual.used_context = True
        return contextual

    def _build_response(self, retrieval: _Retrieval) -> GeneratedResponse:
        decision = retrieval.decision
        to_knowledge = lambda hit: knowledge.to_retrieved_knowledge(retrieval.faqs[hit.key])  # noqa: E731
        if decision.outcome == "answer":
            return self.generator.answer(to_knowledge(decision.best))
        if decision.outcome == "clarification":
            return self.generator.clarification([to_knowledge(hit) for hit in decision.candidates])
        return self.generator.fallback()

    # -- public API ------------------------------------------------------
    def process_message(self, conversation: Conversation, raw_text: str) -> ChatResult:
        """Run the full pipeline. Raises PreprocessingError or ModelUnavailableError."""
        started = time.perf_counter()
        processed = preprocess(raw_text)

        small_talk = detect_small_talk(processed.cleaned)
        retrieval = None
        if small_talk:
            response = self.generator.small_talk(small_talk)
            intent = IntentResult(Intent.UNKNOWN, 0.0)
        else:
            retrieval = self._retrieve_with_context(conversation, processed.cleaned)
            response = self._build_response(retrieval)
            intent = retrieval.intent

        decision = retrieval.decision if retrieval else None
        best = decision.best if decision else None
        score = round(best.score, 4) if best else None
        faq = retrieval.faqs.get(best.key) if (retrieval and best and response.response_type == "answer") else None
        response_time_ms = round((time.perf_counter() - started) * 1000, 2)

        metadata = {
            "sources": response.sources,
            "suggestions": response.suggestions,
            "related": knowledge.related_faqs(faq) if faq else [],
            "disclaimer": response.disclaimer,
            "is_verified": response.is_verified,
            "verification_status": response.verification_status,
            "intent_label": intent.label,
            "used_context": bool(retrieval and retrieval.used_context),
            "matched_question": best.matched_text if faq else None,
            "response_time_ms": response_time_ms,
            "top_candidates": [
                {"faq_id": hit.key, "score": round(hit.score, 4), "matched_text": hit.matched_text}
                for hit in (decision.candidates if decision else [])
            ],
        }

        with transaction.atomic():
            user_message = Message.objects.create(
                conversation=conversation,
                sender_type=Message.SenderType.USER,
                content=processed.original.strip(),
            )
            bot_message = Message.objects.create(
                conversation=conversation,
                sender_type=Message.SenderType.BOT,
                content=response.content,
                detected_intent=intent.intent,
                intent_confidence=intent.confidence,
                similarity_score=score,
                retrieved_faq=faq,
                response_type=response.response_type,
                answered=response.answered,
                information_type=response.information_type or "",
                metadata=metadata,
            )
            if not conversation.title:
                conversation.title = processed.cleaned[:80]
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["title", "updated_at"])
            record_query(
                original_question=processed.original.strip(),
                normalized_question=processed.cleaned,
                conversation=conversation,
                message=bot_message,
                detected_intent=intent.intent,
                intent_confidence=intent.confidence,
                retrieved_faq=faq,
                similarity_score=score,
                response_type=response.response_type,
                answered=response.answered,
                used_context=metadata["used_context"],
                response_time_ms=response_time_ms,
            )
        return ChatResult(user_message, bot_message, response, response_time_ms)


_service = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service
