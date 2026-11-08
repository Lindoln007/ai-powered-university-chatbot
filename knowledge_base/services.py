"""Knowledge base business logic: embedding persistence and semantic retrieval.

Embeddings are stored in PostgreSQL (JSONField) next to the text they were
computed from, together with a fingerprint of that text. An embedding is only
recomputed when its text (or the model) changes, so the knowledge base is not
re-encoded on every request.

For fast search, the stored vectors of all *retrievable* records are loaded
into an in-memory ``SemanticIndex``. The index is rebuilt automatically when
the knowledge base changes (detected via a cheap database fingerprint).
"""

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
from django.conf import settings
from django.db.models import Count, Max
from django.utils import timezone

from nlp_engine import embeddings
from nlp_engine.response_generator import RetrievedKnowledge
from nlp_engine.semantic_search import IndexEntry, SearchHit, SemanticIndex

from .models import FAQ, AlternativeQuestion, KnowledgeArticle

logger = logging.getLogger(__name__)

_state = threading.local()


@contextmanager
def suspend_auto_embedding():
    """Temporarily disable signal-driven embedding refresh (used by bulk imports)."""
    previous = getattr(_state, "suspended", False)
    _state.suspended = True
    try:
        yield
    finally:
        _state.suspended = previous


def auto_embedding_enabled() -> bool:
    return settings.KNOWLEDGE_AUTO_EMBED and not getattr(_state, "suspended", False)


# ---------------------------------------------------------------------------
# Embedding persistence
# ---------------------------------------------------------------------------
@dataclass
class _PendingEmbedding:
    model: type
    pk: int
    text: str
    vector_field: str


def _is_stale(stored_hash: str, stored_vector, text: str, force: bool) -> bool:
    return force or stored_vector is None or stored_hash != embeddings.text_fingerprint(text)


def _write_embeddings(pending: list[_PendingEmbedding]) -> int:
    if not pending:
        return 0
    vectors = embeddings.encode([item.text for item in pending])
    now = timezone.now()
    for item, vector in zip(pending, vectors):
        item.model.objects.filter(pk=item.pk).update(**{
            item.vector_field: embeddings.to_storage(vector),
            "embedding_hash": embeddings.text_fingerprint(item.text),
            "embedding_model": settings.NLP_MODEL_NAME,
            "updated_at": now,
        })
    invalidate_indexes()
    return len(pending)


def _collect_faq(faq: FAQ, force: bool) -> list[_PendingEmbedding]:
    pending = []
    if _is_stale(faq.embedding_hash, faq.question_embedding, faq.question, force):
        pending.append(_PendingEmbedding(FAQ, faq.pk, faq.question, "question_embedding"))
    for alternative in faq.alternative_questions.all():
        pending.extend(_collect_alternative(alternative, force))
    return pending


def _collect_alternative(alternative: AlternativeQuestion, force: bool) -> list[_PendingEmbedding]:
    if _is_stale(alternative.embedding_hash, alternative.embedding, alternative.question_text, force):
        return [_PendingEmbedding(AlternativeQuestion, alternative.pk, alternative.question_text, "embedding")]
    return []


def _collect_article(article: KnowledgeArticle, force: bool) -> list[_PendingEmbedding]:
    if _is_stale(article.embedding_hash, article.embedding, article.embedding_text, force):
        return [_PendingEmbedding(KnowledgeArticle, article.pk, article.embedding_text, "embedding")]
    return []


def refresh_faq_embeddings(faq: FAQ, force: bool = False) -> int:
    """(Re)compute embeddings for an FAQ's question and alternatives whose text changed."""
    return _write_embeddings(_collect_faq(faq, force))


def refresh_alternative_embedding(alternative: AlternativeQuestion, force: bool = False) -> int:
    return _write_embeddings(_collect_alternative(alternative, force))


def refresh_article_embedding(article: KnowledgeArticle, force: bool = False) -> int:
    return _write_embeddings(_collect_article(article, force))


def refresh_all_embeddings(force: bool = False) -> dict:
    """Batch-refresh every stale embedding in the knowledge base. Returns counts per record type."""
    faq_pending, alt_pending, article_pending = [], [], []
    for faq in FAQ.objects.only("id", "question", "question_embedding", "embedding_hash"):
        if _is_stale(faq.embedding_hash, faq.question_embedding, faq.question, force):
            faq_pending.append(_PendingEmbedding(FAQ, faq.pk, faq.question, "question_embedding"))
    for alternative in AlternativeQuestion.objects.only("id", "question_text", "embedding", "embedding_hash"):
        alt_pending.extend(_collect_alternative(alternative, force))
    for article in KnowledgeArticle.objects.all():
        article_pending.extend(_collect_article(article, force))
    _write_embeddings(faq_pending + alt_pending + article_pending)
    return {"faqs": len(faq_pending), "alternatives": len(alt_pending), "articles": len(article_pending)}


# ---------------------------------------------------------------------------
# In-memory search indexes
# ---------------------------------------------------------------------------
_index_lock = threading.Lock()
_indexes: dict[tuple, tuple] = {}
_index_version = 0


def invalidate_indexes() -> None:
    global _index_version
    with _index_lock:
        _index_version += 1
        _indexes.clear()


def _fingerprint(model) -> tuple:
    aggregate = model.objects.aggregate(count=Count("id"), latest=Max("updated_at"))
    return aggregate["count"], aggregate["latest"]


def _cached_index(name: str, demo_mode: bool, fingerprint: tuple, builder) -> SemanticIndex:
    cache_key = (name, demo_mode)
    with _index_lock:
        cached = _indexes.get(cache_key)
        version = _index_version
    if cached and cached[0] == (fingerprint, version):
        return cached[1]
    index = builder()
    with _index_lock:
        if version == _index_version:
            _indexes[cache_key] = ((fingerprint, version), index)
    return index


def _build_faq_index(demo_mode: bool) -> SemanticIndex:
    faqs = list(FAQ.objects.retrievable(demo_mode).only("id", "question", "question_embedding", "embedding_hash"))
    if any(f.question_embedding is None for f in faqs) or AlternativeQuestion.objects.filter(
            faq__in=faqs, embedding__isnull=True).exists():
        # Self-healing: compute embeddings that are missing (e.g. saved while the model was unavailable).
        pending = []
        for faq in FAQ.objects.filter(pk__in=[f.pk for f in faqs]).prefetch_related("alternative_questions"):
            pending.extend(_collect_faq(faq, force=False))
        _write_embeddings(pending)
        faqs =list(FAQ.objects.retrievable(demo_mode).only("id", "question", "question_embedding"))

    entries, vectors = [], []
    for faq in faqs:
        entries.append(IndexEntry(faq.pk, faq.question, "question"))
        vectors.append(faq.question_embedding)
    alternatives = AlternativeQuestion.objects.filter(faq__in=[f.pk for f in faqs], embedding__isnull=False)
    for alternative in alternatives.only("faq_id", "question_text", "embedding"):
        entries.append(IndexEntry(alternative.faq_id, alternative.question_text, "alternative"))
        vectors.append(alternative.embedding)
    matrix = np.asarray(vectors, dtype=np.float32) if vectors else np.zeros((0, embeddings.EMBEDDING_DIMENSION))
    return SemanticIndex(entries, matrix)


def _build_article_index(demo_mode: bool) -> SemanticIndex:
    articles = KnowledgeArticle.objects.retrievable(demo_mode)
    for article in articles.filter(embedding__isnull=True):
        refresh_article_embedding(article)
    entries, vectors = [], []
    for article in KnowledgeArticle.objects.retrievable(demo_mode).filter(embedding__isnull=False):
        entries.append(IndexEntry(article.pk, article.title, "article"))
        vectors.append(article.embedding)
    matrix = np.asarray(vectors, dtype=np.float32) if vectors else np.zeros((0, embeddings.EMBEDDING_DIMENSION))
    return SemanticIndex(entries, matrix)


def get_faq_index(demo_mode: bool | None = None) -> SemanticIndex:
    demo_mode = settings.CHATBOT_DEMO_MODE if demo_mode is None else demo_mode
    fingerprint = _fingerprint(FAQ) + _fingerprint(AlternativeQuestion)
    return _cached_index("faq", demo_mode, fingerprint, lambda: _build_faq_index(demo_mode))


def get_article_index(demo_mode: bool | None = None) -> SemanticIndex:
    demo_mode = settings.CHATBOT_DEMO_MODE if demo_mode is None else demo_mode
    return _cached_index("article", demo_mode, _fingerprint(KnowledgeArticle),
                         lambda: _build_article_index(demo_mode))


# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------
def search_faqs(query_embedding: np.ndarray, top_k: int | None = None,
                demo_mode: bool | None = None) -> list[SearchHit]:
    return get_faq_index(demo_mode).search(query_embedding, top_k or settings.CHATBOT_TOP_K)


def search_articles(query_embedding: np.ndarray, top_k: int = 5, demo_mode: bool | None = None) -> list[SearchHit]:
    return get_article_index(demo_mode).search(query_embedding, top_k)


def to_retrieved_knowledge(faq: FAQ) -> RetrievedKnowledge:
    return RetrievedKnowledge(
        id=faq.pk,
        reference_code=faq.reference_code,
        question=faq.question,
        answer=faq.answer,
        category=faq.category.name,
        information_type=faq.information_type,
        verification_status=faq.verification_status,
        source_description=faq.source_description,
        source_url=faq.source_url,
    )


def load_faqs(ids: list[int]) -> dict[int, FAQ]:
    return {faq.pk: faq for faq in FAQ.objects.filter(pk__in=ids).select_related("category")}
