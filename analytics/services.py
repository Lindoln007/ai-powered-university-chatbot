"""Analytics calculated from stored records (nothing is estimated or hard-coded)."""

from datetime import date, datetime, time

import numpy as np
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Max, Min, Q
from django.db.models.functions import Lower, TruncDate, TruncMonth
from django.utils import timezone

from chat.models import Conversation, Message
from feedback.models import ChatbotFeedback

from .models import QueryAnalytics


def record_query(*, original_question, normalized_question, conversation, message, detected_intent,
                 intent_confidence, retrieved_faq, similarity_score, response_type, answered, used_context,
                 response_time_ms) -> QueryAnalytics:
    review_status = (QueryAnalytics.ReviewStatus.PENDING if response_type == QueryAnalytics.ResponseType.FALLBACK
                     else QueryAnalytics.ReviewStatus.NOT_APPLICABLE)
    return QueryAnalytics.objects.create(
        original_question=original_question,
        normalized_question=normalized_question,
        conversation=conversation,
        message=message,
        detected_intent=detected_intent,
        intent_confidence=intent_confidence,
        retrieved_faq=retrieved_faq,
        category=retrieved_faq.category if retrieved_faq else None,
        similarity_score=similarity_score,
        answered=answered,
        response_type=response_type,
        used_context=used_context,
        response_time_ms=response_time_ms,
        review_status=review_status,
    )


class DateRange:
    """Inclusive date range used to filter analytics (either bound may be None)."""

    def __init__(self, start: date | None = None, end: date | None = None):
        tz = timezone.get_current_timezone()
        self.start = timezone.make_aware(datetime.combine(start, time.min), tz) if start else None
        self.end = timezone.make_aware(datetime.combine(end, time.max), tz) if end else None

    def filter(self, queryset, field: str):
        if self.start:
            queryset = queryset.filter(**{f"{field}__gte": self.start})
        if self.end:
            queryset = queryset.filter(**{f"{field}__lte": self.end})
        return queryset

    def as_dict(self):
        return {"start": self.start.date() if self.start else None, "end": self.end.date() if self.end else None}


def _queries(date_range: DateRange):
    return date_range.filter(QueryAnalytics.objects.all(), "timestamp")


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def overview(date_range: DateRange) -> dict:
    queries = _queries(date_range)
    counts = queries.aggregate(
        total=Count("id"),
        answered=Count("id", filter=Q(response_type=QueryAnalytics.ResponseType.ANSWER)),
        unanswered=Count("id", filter=Q(response_type=QueryAnalytics.ResponseType.FALLBACK)),
        clarifications=Count("id", filter=Q(response_type=QueryAnalytics.ResponseType.CLARIFICATION)),
        small_talk=Count("id", filter=Q(response_type=QueryAnalytics.ResponseType.SMALL_TALK)),
        context_used=Count("id", filter=Q(used_context=True)),
        avg_response=Avg("response_time_ms"),
        avg_similarity=Avg("similarity_score", filter=Q(response_type=QueryAnalytics.ResponseType.ANSWER)),
    )
    feedback = date_range.filter(ChatbotFeedback.objects.all(), "created_at").aggregate(
        total=Count("id"),
        positive=Count("id", filter=Q(rating__gte=ChatbotFeedback.POSITIVE_MIN_RATING)),
        negative=Count("id", filter=Q(rating__lte=ChatbotFeedback.NEGATIVE_MAX_RATING)),
        average=Avg("rating"),
    )
    questions = counts["total"] - counts["small_talk"]
    return {
        "date_range": date_range.as_dict(),
        "total_registered_users": date_range.filter(get_user_model().objects.all(), "date_joined").count(),
        "total_conversations": date_range.filter(Conversation.objects.all(), "created_at").count(),
        "total_messages": date_range.filter(Message.objects.all(), "created_at").count(),
        "total_chatbot_questions": counts["total"],
        "answered_questions": counts["answered"],
        "unanswered_questions": counts["unanswered"],
        "clarification_requests": counts["clarifications"],
        "small_talk_messages": counts["small_talk"],
        "context_assisted_answers": counts["context_used"],
        "answer_rate": _ratio(counts["answered"], questions),
        "average_response_time_ms": round(counts["avg_response"] or 0, 2),
        "average_answer_similarity": round(counts["avg_similarity"] or 0, 4),
        "feedback": {
            "total": feedback["total"],
            "positive": feedback["positive"],
            "negative": feedback["negative"],
            "neutral": feedback["total"] - feedback["positive"] - feedback["negative"],
            "average_rating": round(feedback["average"] or 0, 2),
        },
    }


def popular_questions(date_range: DateRange, limit: int = 10) -> dict:
    queries = _queries(date_range)
    top_faqs = (
        queries.filter(retrieved_faq__isnull=False)
        .values("retrieved_faq", "retrieved_faq__reference_code", "retrieved_faq__question",
                "retrieved_faq__category__name")
        .annotate(times_asked=Count("id"), average_similarity=Avg("similarity_score"), last_asked=Max("timestamp"))
        .order_by("-times_asked", "retrieved_faq")[:limit]
    )
    top_phrasings = (
        queries.exclude(response_type=QueryAnalytics.ResponseType.SMALL_TALK)
        .annotate(question=Lower("normalized_question"))
        .values("question")
        .annotate(times_asked=Count("id"), last_asked=Max("timestamp"))
        .order_by("-times_asked", "question")[:limit]
    )
    return {
        "date_range": date_range.as_dict(),
        "most_frequently_answered_faqs": [
            {
                "faq_id": row["retrieved_faq"],
                "reference_code": row["retrieved_faq__reference_code"],
                "question": row["retrieved_faq__question"],
                "category": row["retrieved_faq__category__name"],
                "times_asked": row["times_asked"],
                "average_similarity": round(row["average_similarity"] or 0, 4),
                "last_asked": row["last_asked"],
            }
            for row in top_faqs
        ],
        "most_frequent_questions": list(top_phrasings),
    }


def unanswered_summary(date_range: DateRange, limit: int = 20) -> list[dict]:
    rows = (
        _queries(date_range).filter(response_type=QueryAnalytics.ResponseType.FALLBACK,
                                    review_status=QueryAnalytics.ReviewStatus.PENDING)
        .annotate(question=Lower("normalized_question"))
        .values("question")
        .annotate(times_asked=Count("id"), last_asked=Max("timestamp"), best_similarity=Max("similarity_score"))
        .order_by("-times_asked", "-last_asked")[:limit]
    )
    return [{**row, "best_similarity": round(row["best_similarity"] or 0, 4)} for row in rows]


def category_statistics(date_range: DateRange) -> dict:
    queries = _queries(date_range)
    by_category = (
        queries.filter(category__isnull=False)
        .values("category", "category__name")
        .annotate(
            questions=Count("id"),
            average_similarity=Avg("similarity_score"),
            positive_feedback=Count("id", filter=Q(message__feedback__rating__gte=ChatbotFeedback.POSITIVE_MIN_RATING)),
            negative_feedback=Count("id", filter=Q(message__feedback__rating__lte=ChatbotFeedback.NEGATIVE_MAX_RATING)),
        )
        .order_by("-questions", "category__name")
    )
    by_intent = (
        queries.exclude(response_type=QueryAnalytics.ResponseType.SMALL_TALK)
        .values("detected_intent")
        .annotate(questions=Count("id"),
                  answered=Count("id", filter=Q(response_type=QueryAnalytics.ResponseType.ANSWER)))
        .order_by("-questions", "detected_intent")
    )
    return {
        "date_range": date_range.as_dict(),
        "categories": [
            {
                "category_id": row["category"],
                "category": row["category__name"],
                "answered_questions": row["questions"],
                "average_similarity": round(row["average_similarity"] or 0, 4),
                "positive_feedback": row["positive_feedback"],
                "negative_feedback": row["negative_feedback"],
            }
            for row in by_category
        ],
        "intents": [
            {**row, "answer_rate": _ratio(row["answered"], row["questions"])} for row in by_intent
        ],
    }


def usage(date_range: DateRange) -> dict:
    queries = _queries(date_range)

    def series(trunc):
        rows = (queries.annotate(period=trunc("timestamp")).values("period")
                .annotate(questions=Count("id"),
                          answered=Count("id", filter=Q(response_type=QueryAnalytics.ResponseType.ANSWER)),
                          unanswered=Count("id", filter=Q(response_type=QueryAnalytics.ResponseType.FALLBACK)),
                          conversations=Count("conversation", distinct=True))
                .order_by("period"))
        return [{**row, "period": row["period"].isoformat()[:10] if row["period"] else None} for row in rows]

    return {"date_range": date_range.as_dict(), "daily": series(TruncDate), "monthly": series(TruncMonth)}


def response_performance(date_range: DateRange) -> dict:
    queries = _queries(date_range)
    stats = queries.aggregate(average=Avg("response_time_ms"), minimum=Min("response_time_ms"),
                              maximum=Max("response_time_ms"), count=Count("id"))
    times = np.fromiter(queries.values_list("response_time_ms", flat=True), dtype=float)
    by_type = (queries.values("response_type")
               .annotate(count=Count("id"), average_response_time_ms=Avg("response_time_ms"),
                         average_similarity=Avg("similarity_score"))
               .order_by("response_type"))
    return {
        "date_range": date_range.as_dict(),
        "total_queries": stats["count"],
        "average_response_time_ms": round(stats["average"] or 0, 2),
        "min_response_time_ms": round(stats["minimum"] or 0, 2),
        "max_response_time_ms": round(stats["maximum"] or 0, 2),
        "median_response_time_ms": round(float(np.percentile(times, 50)), 2) if times.size else 0,
        "p95_response_time_ms": round(float(np.percentile(times, 95)), 2) if times.size else 0,
        "by_response_type": [
            {
                "response_type": row["response_type"],
                "count": row["count"],
                "average_response_time_ms": round(row["average_response_time_ms"] or 0, 2),
                "average_similarity": round(row["average_similarity"], 4) if row["average_similarity"] else None,
            }
            for row in by_type
        ],
        **{key: value for key, value in usage(date_range).items() if key != "date_range"},
    }
