"""Retrieval-based response generation.

Responses are composed only from knowledge base records that semantic search
retrieved. Nothing is generated freely, so the chatbot cannot fabricate facts.
Hypothetical (demonstration / unverified) records are always labelled.

The ``ResponseGenerator`` class is the single place to change if an optional
LLM-based paraphrasing step is added in the future; any such step must keep
the factual content grounded in the retrieved record.
"""

from dataclasses import dataclass, field

FALLBACK_MESSAGE = (
    "I'm sorry, I couldn't find verified information about that question in the university "
    "knowledge base. Please contact the relevant university department for assistance."
)

DEMONSTRATION_DISCLAIMER = (
    "This is hypothetical demonstration information prepared for an academic prototype. "
    "It is not official information from {institution}. Please confirm with the university."
)
UNVERIFIED_DISCLAIMER = (
    "This information has not yet been verified by {institution}. Please confirm with the relevant office."
)

SMALL_TALK_RESPONSES = {
    "greeting": (
        "Hello! I can answer questions about university programmes, admissions, fees, registration, "
        "examinations, the academic calendar, library services, accommodation and student support. "
        "What would you like to know?"
    ),
    "thanks": "You're welcome! Feel free to ask another question about the university.",
    "goodbye": "Goodbye! Come back any time you have a question about the university.",
}


@dataclass(frozen=True)
class RetrievedKnowledge:
    """Framework-independent view of a knowledge base record used to build a response."""

    id: int
    reference_code: str
    question: str
    answer: str
    category: str
    information_type: str  # "institutional" or "demonstration"
    verification_status: str  # "verified", "unverified" or "draft"
    source_description: str = ""
    source_url: str = ""

    @property
    def is_verified(self) -> bool:
        return self.verification_status == "verified" and self.information_type == "institutional"


@dataclass
class GeneratedResponse:
    content: str
    response_type: str  # "answer", "clarification", "fallback" or "small_talk"
    answered: bool
    information_type: str | None = None
    verification_status: str | None = None
    is_verified: bool | None = None
    disclaimer: str | None = None
    sources: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)


class ResponseGenerator:
    def __init__(self, institution_name: str):
        self.institution_name = institution_name

    def disclaimer_for(self, knowledge: RetrievedKnowledge) -> str | None:
        if knowledge.is_verified:
            return None
        if knowledge.information_type == "demonstration":
            return DEMONSTRATION_DISCLAIMER.format(institution=self.institution_name)
        return UNVERIFIED_DISCLAIMER.format(institution=self.institution_name)

    @staticmethod
    def source_for(knowledge: RetrievedKnowledge) -> dict:
        return {
            "type": "faq",
            "id": knowledge.id,
            "reference_code": knowledge.reference_code,
            "question": knowledge.question,
            "category": knowledge.category,
            "source_description": knowledge.source_description,
            "source_url": knowledge.source_url or None,
            "information_type": knowledge.information_type,
            "verification_status": knowledge.verification_status,
        }

    def answer(self, knowledge: RetrievedKnowledge) -> GeneratedResponse:
        disclaimer = self.disclaimer_for(knowledge)
        content = knowledge.answer.strip()
        if disclaimer:
            label = "Demonstration information" if knowledge.information_type == "demonstration" else "Unverified information"
            content = f"{content}\n\n[{label}] {disclaimer}"
        return GeneratedResponse(
            content=content,
            response_type="answer",
            answered=True,
            information_type=knowledge.information_type,
            verification_status=knowledge.verification_status,
            is_verified=knowledge.is_verified,
            disclaimer=disclaimer,
            sources=[self.source_for(knowledge)],
        )

    def clarification(self, candidates: list[RetrievedKnowledge]) -> GeneratedResponse:
        options = "\n".join(f"{index}. {item.question}" for index, item in enumerate(candidates, start=1))
        content = (
            "Your question could relate to more than one topic. Did you mean one of the following?\n"
            f"{options}\nPlease rephrase your question or choose one of the options above."
        )
        return GeneratedResponse(
            content=content,
            response_type="clarification",
            answered=False,
            suggestions=[{"faq_id": item.id, "question": item.question, "category": item.category}
                         for item in candidates],
        )

    def fallback(self, suggestions: list[RetrievedKnowledge] | None = None) -> GeneratedResponse:
        return GeneratedResponse(
            content=FALLBACK_MESSAGE,
            response_type="fallback",
            answered=False,
            suggestions=[{"faq_id": item.id, "question": item.question, "category": item.category}
                         for item in (suggestions or [])],
        )

    @staticmethod
    def small_talk(kind: str) -> GeneratedResponse:
        return GeneratedResponse(content=SMALL_TALK_RESPONSES[kind], response_type="small_talk", answered=False)
